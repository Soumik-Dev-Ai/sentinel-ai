"""Critic agent — LLM-as-a-Judge reviews the Coder's output BEFORE execution.

Scoring (0..10) on:
    - correctness       is the algorithm logically sound?
    - edge_cases       are boundaries handled?
    - acceptance       does it satisfy the goal's acceptance criteria?
    - readability      idiomatic, clean code?

If total < ACCEPT_THRESHOLD the critic rejects and returns specific
remediation guidance. The orchestrator loops back to the coder with that
guidance. Otherwise the critic passes the code forward to the executor.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from backend.orchestrator.base import Agent, AgentContext, fail, ok


CRITIC_SYSTEM_PROMPT = """You are CRITIC — LLM-as-a-Judge for Python code.

You receive:
- The user goal + acceptance criteria.
- The latest code submission (filename + full content).
- (Optional) prior critique history if this is a re-review.

Output ONLY this JSON object:

{{
  "correctness": 0-10,
  "edge_cases": 0-10,
  "acceptance": 0-10,
  "readability": 0-10,
  "total": 0-100,
  "passes": true|false,
  "issues": ["specific issue 1", "..."],
  "fix_suggestions": ["specific actionable suggestion 1", "..."],
  "verdict": "ACCEPT"|"REJECT"
}}

Rules:
- Be strict but fair. Issues should be specific enough that the coder can act on them.
- Picklines, silent failure, off-by-one, recursion blow-up, type confusion are all -ve.
- A passing score requires `total >= 80`.
- Do NOT suggest changes that contradict the goal.
"""


ACCEPT_THRESHOLD = 80  # /100 — equivalent to a per-axis >=8 average


class Critic(Agent):
    name = "critic"
    human_label = "Critic"

    def __init__(self, threshold: int = ACCEPT_THRESHOLD) -> None:
        super().__init__()
        self._threshold = threshold

    def run(self, ctx: AgentContext, **kw: Any) -> dict[str, Any]:
        filename = str(kw.get("filename") or ctx.path_to_file or "main.py")
        code = str(kw.get("code") or "")
        prior_issues = kw.get("prior_issues", [])
        node_id = kw.get("node_id") or f"critic_{filename}"

        ctx.bus.emit("agent_started", agent=self.name, label=f"Reviewing: {filename}")
        self.add_graph_node(
            ctx,
            node_id=node_id,
            label=f"⚖️ Review: {filename}",
            agent="critic",
            status="active",
            parent=kw.get("parent_node"),
        )

        user_payload: dict[str, Any] = {
            "goal": ctx.goal,
            "acceptance": ctx.acceptance,
            "filename": filename,
            "code": code,
        }
        if prior_issues:
            user_payload["prior_issues"] = prior_issues

        reply = self._llm_chat(
            ctx,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            stream=True,
        )
        verdict = self._parse_verdict(reply.thought or "")
        if verdict is None:
            self.update_graph_node(ctx, node_id, status="error")
            return fail("unparseable_verdict")

        total = int(verdict.get("total", 0))
        passes = bool(verdict.get("passes", total >= self._threshold))
        verdict_text = str(verdict.get("verdict", "ACCEPT" if passes else "REJECT")).upper()
        if verdict_text not in {"ACCEPT", "REJECT"}:
            verdict_text = "ACCEPT" if passes else "REJECT"

        ctx.bus.emit(
            "critic_verdict",
            filename=filename,
            scores={
                "correctness": verdict.get("correctness", 0),
                "edge_cases": verdict.get("edge_cases", 0),
                "acceptance": verdict.get("acceptance", 0),
                "readability": verdict.get("readability", 0),
                "total": total,
            },
            passes=passes,
            verdict=verdict_text,
            issues=verdict.get("issues", []),
            fix_suggestions=verdict.get("fix_suggestions", []),
        )
        ctx.bus.emit(
            "terminal_line",
            text=(
                f"[CRITIC] {verdict_text} total={total}/100 "
                f"correctness={verdict.get('correctness', 0)} "
                f"edge_cases={verdict.get('edge_cases', 0)} "
                f"acceptance={verdict.get('acceptance', 0)}"
            ),
            line_type="success" if passes else "error",
        )

        self.update_graph_node(
            ctx,
            node_id,
            status="success" if passes else "rejected",
            meta={"total": total, "verdict": verdict_text},
        )
        ctx.bus.emit("agent_finished", agent=self.name, status="ok")

        return ok(
            passes=passes,
            verdict=verdict_text,
            total=total,
            issues=verdict.get("issues", []),
            fix_suggestions=verdict.get("fix_suggestions", []),
            scores={
                "correctness": verdict.get("correctness", 0),
                "edge_cases": verdict.get("edge_cases", 0),
                "acceptance": verdict.get("acceptance", 0),
                "readability": verdict.get("readability", 0),
            },
            node_id=node_id,
        )

    # ---------- parser ----------

    def _parse_verdict(self, text: str) -> Optional[dict[str, Any]]:
        s = self._strip(text)
        try:
            return json.loads(s)
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None

    @staticmethod
    def _strip(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s[3:]
            if s.startswith("json"):
                s = s[4:]
        if s.endswith("```"):
            s = s[:-3]
        return s.strip()
