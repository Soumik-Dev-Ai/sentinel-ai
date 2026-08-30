"""Adaptive retry strategy router — categorizes failures and emits a strategy.

Categorizes an execution failure into one of:

    | category       | strategy           | effect                                          |
    | syntax         | line_patch         | ask coder to patch specific lines (targeted)    |
    | logic          | full_rewrite       | ask coder to rewrite the algorithm from scratch |
    | external       | backoff            | exponential backoff, then re-execute            |

The router is pure: given a `Failure` it returns a `Strategy` record that the
orchestrator pipeline acts on. It does not invoke the LLM itself.
"""
from __future__ import annotations

import enum
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional


class FailureCategory(str, enum.Enum):
    SYNTAX = "syntax"
    LOGIC = "logic"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class Strategy(str, enum.Enum):
    LINE_PATCH = "line_patch"
    FULL_REWRITE = "full_rewrite"
    BACKOFF = "backoff"
    NONE = "none"


@dataclass
class Failure:
    """Unified failure descriptor produced by the Executor."""
    category: FailureCategory
    exception: str
    line: Optional[int]
    stderr: str
    stdout: str = ""
    exit_code: int = -1
    suggestions: list[str] = field(default_factory=list)


@dataclass
class StrategyResult:
    strategy: Strategy
    failure: Failure
    wait_seconds: float = 0.0
    guidance: str = ""
    attempt_index: int = 0
    historical_rate: Optional[float] = None  # RAG success rate for this signature


# Mapping from category -> default strategy
_CATEGORY_TO_STRATEGY = {
    FailureCategory.SYNTAX: Strategy.LINE_PATCH,
    FailureCategory.LOGIC: Strategy.FULL_REWRITE,
    FailureCategory.EXTERNAL: Strategy.BACKOFF,
    FailureCategory.UNKNOWN: Strategy.FULL_REWRITE,
}


# -----------------------------------------------------------------------------
# Failure classification
# -----------------------------------------------------------------------------

# Heuristic exception-class lists.
_SYNTAX_ERRORS = {"SyntaxError", "IndentationError", "TabError", "TokenError"}
_LOGIC_ERRORS = {
    "AssertionError", "ValueError", "TypeError", "IndexError", "KeyError",
    "ZeroDivisionError", "AttributeError", "NameError", "UnboundLocalError",
    "RecursionError", "StopIteration", "NotImplementedError", "ArithmeticError",
    "LookupError", "ReferenceError",
}
_EXTERNAL_ERRORS = {
    "TimeoutError", "ConnectionError", "ConnectionRefusedError",
    "ConnectionAbortedError", "ConnectionResetError", "OSError", "IOError",
    "FileNotFoundError", "PermissionError", "PermissionDeniedError", "BlockingIOError",
    "HTTPError", "URLError", "JSONDecodeError",  # http-ish
}


def classify(execution_result: dict[str, Any]) -> Failure:
    """Build a `Failure` from the executor's result envelope."""
    parsed = execution_result.get("parsed_traceback") or {}
    exception = str(parsed.get("exception") or "")
    line = parsed.get("line")
    stderr = str(execution_result.get("stderr") or "")
    stdout = str(execution_result.get("stdout") or "")
    exit_code = int(execution_result.get("exit_code", -1))
    category = FailureCategory.UNKNOWN

    if exception in _SYNTAX_ERRORS:
        category = FailureCategory.SYNTAX
    elif exception in _EXTERNAL_ERRORS:
        category = FailureCategory.EXTERNAL
    elif exception in _LOGIC_ERRORS:
        category = FailureCategory.LOGIC
    elif exception:
        # Unknown-but-present error — treat as logic.
        category = FailureCategory.LOGIC

    # No exception parsed but non-zero exit -> treat timeout/no-output as external.
    if category == FailureCategory.UNKNOWN and exit_code in (124, 137):
        category = FailureCategory.EXTERNAL

    return Failure(
        category=category,
        exception=exception or "<unknown>",
        line=line,
        stderr=stderr,
        stdout=stdout,
        exit_code=exit_code,
    )


# -----------------------------------------------------------------------------
# Strategy router
# -----------------------------------------------------------------------------

class RetryRouter:
    """Decides the next strategy + retry policy.

    call emit_strategy_through() via run(); the orchestrator then uses the
    returned strategy to drive the next coder/executor iteration.

    Maintains per-subtask attempt counters so we can apply exponential
    backoff specifically for EXTERNAL failures (networky).
    """

    def __init__(
        self,
        max_attempts_per_subtask: int = 3,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
        backoff_jitter: float = 0.3,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._backoff_jitter = backoff_jitter
        self._max_attempts = max_attempts_per_subtask
        self._attempts: dict[str, int] = {}
        self._rng = rng or random.Random()

    def reset(self, subtask_id: str) -> None:
        self._attempts[subtask_id] = 0

    def attempts(self, subtask_id: str) -> int:
        return self._attempts.get(subtask_id, 0)

    def next_strategy(
        self,
        subtask_id: str,
        failure: Failure,
        historical_rate: Optional[float] = None,
    ) -> StrategyResult:
        self._attempts[subtask_id] = self._attempts.get(subtask_id, 0) + 1
        attempt_index = self._attempts[subtask_id]
        strategy = _CATEGORY_TO_STRATEGY.get(failure.category, Strategy.FULL_REWRITE)

        wait_seconds = 0.0
        if strategy == Strategy.BACKOFF:
            wait_seconds = min(
                self._backoff_max,
                self._backoff_base * (2 ** (attempt_index - 1)),
            )
            if self._backoff_jitter:
                wait_seconds += self._rng.uniform(0, self._backoff_jitter * wait_seconds)

        guidance = self._build_guidance(strategy, failure, attempt_index)

        return StrategyResult(
            strategy=strategy,
            failure=failure,
            wait_seconds=wait_seconds,
            guidance=guidance,
            attempt_index=attempt_index,
            historical_rate=historical_rate,
        )

    @staticmethod
    def _build_guidance(strategy: Strategy, f: Failure, attempt: int) -> str:
        if strategy == Strategy.LINE_PATCH:
            loc = f"at or near line {f.line}" if f.line else "in the file"
            return (
                f"SyntaxError detected {loc} ({f.exception}). "
                f"Patch ONLY the offending lines; do not rewrite the entire file. "
                f"Likely causes: indentation, missing ':' on compound statements, "
                f"unbalanced parentheses / quotes / brackets, or reserved-word misuse. "
                f"Show the corrected lines only in the new code file."
            )
        if strategy == Strategy.FULL_REWRITE:
            return (
                f"Logic failure ({f.exception}) — the algorithm is wrong. "
                f"Perform a complete rewrite of the implementation. "
                f"Reconsider: input validation, loop bounds, base cases, "
                f"return types, off-by-one errors. stderr dump:\n{f.stderr[:800]}"
            )
        if strategy == Strategy.BACKOFF:
            return (
                f"External/environment failure ({f.exception}) — backoff attempt #{attempt}. "
                "Re-invoke the operation after the wait elapses; do not change the code unless "
                "the error persists after 3 attempts."
            )
        return ""

    def is_exhausted(self, subtask_id: str) -> bool:
        return self._attempts.get(subtask_id, 0) >= self._max_attempts

    def guidance_for_export(
        self,
        strategy_result: StrategyResult,
    ) -> dict[str, Any]:
        """For memory writes — convert a strategy result into a serializable dict."""
        return {
            "category": strategy_result.failure.category.value,
            "exception": strategy_result.failure.exception,
            "strategy": strategy_result.strategy.value,
            "guidance": strategy_result.guidance,
            "wait_seconds": strategy_result.wait_seconds,
            "attempt_index": strategy_result.attempt_index,
        }
