"""Token / cost accounting shared across all Sentinel AI 2.0 agents.

Tracks input + output tokens per LLM call, derives a USD cost from a configurable
pricing table (Claude 3.5 Sonnet / DeepSeek defaults), and emits telemetry events
that are streamed to the frontend via the WebSocket server.

Designed to be process-wide and thread-safe (Python agents run in a
ThreadPoolExecutor, so the counters use a Lock).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# Per-million-token USD pricing for the providers we route through.
# Update as provider pricing changes.
DEFAULT_PRICING_USD_PER_MTok: dict[str, dict[str, float]] = {
    # Anthropic Claude 3.5 Sonnet (openrouter wrapper treats as claude-3.5-sonnet)
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    # DeepSeek-V3 (cheap, strong at code)
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
    # Groq Llama 3.3 70B (free tier in many cases; nominal pricing)
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    # NVIDIA NIM Llama 3.1 70B
    "meta/llama-3.1-70b-instruct": {"input": 0.64, "output": 0.64},
    # Local Ollama — free
    "local-ollama": {"input": 0.0, "output": 0.0},
    # Generic fallback
    "default": {"input": 1.00, "output": 3.00},
}


@dataclass
class UsageRecord:
    """A single LLM call's metering snapshot."""
    agent: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "ts": self.ts,
        }


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: Optional[dict[str, dict[str, float]]] = None,
) -> float:
    """Estimate USD cost for a single call."""
    table = pricing if pricing is not None else DEFAULT_PRICING_USD_PER_MTok
    rate = table.get(model) or table.get("default")
    in_cost = (input_tokens / 1_000_000.0) * rate["input"]
    out_cost = (output_tokens / 1_000_000.0) * rate["output"]
    return round(in_cost + out_cost, 6)


class TokenBudget:
    """Hard ceiling on tokens *or* USD for a single agent run.

    Used by the orchestrator to abort a subtask if the run becomes financially
    unreasonable.
    """

    def __init__(
        self,
        max_total_tokens: Optional[int] = None,
        max_total_cost_usd: Optional[float] = None,
    ):
        self.max_total_tokens = max_total_tokens
        self.max_total_cost_usd = max_total_cost_usd

    def is_exhausted(self, used_tokens: int, used_cost: float) -> tuple[bool, str]:
        if self.max_total_tokens is not None and used_tokens >= self.max_total_tokens:
            return True, f"token budget exhausted ({used_tokens}/{self.max_total_tokens})"
        if self.max_total_cost_usd is not None and used_cost >= self.max_total_cost_usd:
            return True, f"cost budget exhausted (${used_cost:.4f}/${self.max_total_cost_usd:.4f})"
        return False, ""


class CostTracker:
    """Thread-safe accumulation of token usage + cost across all agents.

    The WebSocket server polls `snapshot()` periodically to push
    `telemetry_update` events to the frontend.
    """

    def __init__(
        self,
        budget: Optional[TokenBudget] = None,
        on_record: Optional[Callable[[UsageRecord], None]] = None,
    ):
        self._lock = threading.Lock()
        self._records: list[UsageRecord] = []
        self._total_input = 0
        self._total_output = 0
        self._total_cost = 0.0
        self._per_agent: dict[str, dict[str, int]] = {}
        self._budget = budget or TokenBudget()
        self._on_record = on_record

    def record(
        self,
        agent: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageRecord:
        """Record one LLM call. Returns the UsageRecord; the caller may emit it."""
        input_tokens = max(0, int(input_tokens))
        output_tokens = max(0, int(output_tokens))
        cost = estimate_cost_usd(model, input_tokens, output_tokens)

        rec = UsageRecord(
            agent=agent,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        with self._lock:
            self._records.append(rec)
            self._total_input += input_tokens
            self._total_output += output_tokens
            self._total_cost += cost
            agg = self._per_agent.setdefault(
                agent, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
            )
            agg["input_tokens"] += input_tokens
            agg["output_tokens"] += output_tokens
            agg["cost_usd"] = round(agg["cost_usd"] + cost, 6)
            agg["calls"] += 1
        if self._on_record is not None:
            try:
                self._on_record(rec)
            except Exception:
                # Listener must not break the call path.
                pass
        return rec

    def record_from_reply(
        self,
        agent: str,
        provider: str,
        model: str,
        reply_usage: dict[str, int],
    ) -> UsageRecord:
        """Convenience wrapper that pulls input/output tokens from a Reply.usage dict."""
        return self.record(
            agent=agent,
            provider=provider,
            model=model,
            input_tokens=int(reply_usage.get("input_tokens", reply_usage.get("prompt_tokens", 0))),
            output_tokens=int(reply_usage.get("output_tokens", reply_usage.get("completion_tokens", 0))),
        )

    def snapshot(self) -> dict[str, Any]:
        """Immutable telemetry snapshot suitable for sending over the wire."""
        with self._lock:
            per_agent = {a: dict(v) for a, v in self._per_agent.items()}
            total_tokens = self._total_input + self._total_output
            used_cost = round(self._total_cost, 6)
            budget_remaining_tokens: Optional[int] = None
            budget_remaining_usd: Optional[float] = None
            if self._budget.max_total_tokens is not None:
                budget_remaining_tokens = max(0, self._budget.max_total_tokens - total_tokens)
            if self._budget.max_total_cost_usd is not None:
                budget_remaining_usd = round(
                    max(0.0, self._budget.max_total_cost_usd - used_cost), 6
                )
            exhausted, reason = self._budget.is_exhausted(total_tokens, used_cost)
            return {
                "total_input_tokens": self._total_input,
                "total_output_tokens": self._total_output,
                "total_tokens": total_tokens,
                "total_cost_usd": used_cost,
                "per_agent": per_agent,
                "budget_remaining_tokens": budget_remaining_tokens,
                "budget_remaining_usd": budget_remaining_usd,
                "budget_exhausted": exhausted,
                "budget_reason": reason,
                "calls": len(self._records),
            }

    @property
    def budget(self) -> TokenBudget:
        return self._budget

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._total_input = 0
            self._total_output = 0
            self._total_cost = 0.0
            self._per_agent.clear()
