"""Orchestrator agent — decomposes the user's goal into subtasks via Tree-of-Thought.

Workflow:
    1. Generate N=3 distinct approach paths for the goal.
    2. Score each path with an "approach confidence" 0..1.
    3. Keep the highest-scoring path and split it into a list of subtasks.
    4. Route each subtask to the appropriate specialist agent (Coder / Executor).

The orchestrator emits graph_node / agent_started / agent_finished events so
the live execution graph in the frontend can grow over time.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.orchestrator.base import Agent, AgentContext, fail, ok


ORCH_SYSTEM_PROMPT = """You are ORCHESTRATOR, the strategic planner of a multi-agent system that writes Python code.

Your job: for any user goal, generate 3 distinct *approach paths* and score each.

You receive:
- A user goal.
- (Optional) acceptance criteria.

You MUST respond with ONLY a JSON object of this shape (no prose before/after):

{
  "paths": [
    {
      "id": "P1",
      "description": "short description of the approach",
      "steps": ["subtask 1 desc", "subtask 2 desc", "..."],
      "confidence": 0.85,           // 0..1, your belief it will succeed
      "rationale": "one-line rationale",
      "risks": ["risk 1", "..."]
    },
    // ... 3 paths total
  ]
}

Scoring rules:
- Prefer simple, correct, observable solutions over clever ones.
- Steps must be specific executable subtasks like "write fib.py to compute nth Fibonacci iteratively".
- Confidence reflects: code correctness probability * ease of verification * approach match to goal.
- Reduce confidence for: requires external network calls (less reliable), needs large library dependencies, has unclear acceptance.

Always output exactly 3 paths, ordered by your predicted confidence (highest first).
"""


EXEC_PLAN_PROMPT = """Given the chosen approach below, expand it into a precise ordered list of subtasks for the team.

CHOSEN APPROACH:
{chosen}

Respond with ONLY a JSON object:
{{
  "subtasks": [
    {{"id": "S1", "desc": "concise description", "agent": "coder", "model_tier": "coding"}},
    {{"id": "S2", "desc": "run unit tests", "agent": "executor", "model_tier": "fast_eval"}},
    ...
  ]
}}

Rules:
- IDs must be S1, S2, S3, ... in execution order.
- `agent` must be one of: coder, executor, critic.
- `model_tier` MUST be selected based on complexity:
   * `strategic` - High intelligence needed (complex reasoning, planning)
   * `coding` - Deep code generation or logic refactoring
   * `fast_eval` - Simple tasks, traceback parsing, unit tests, fast feedback
- The Coder writes/edits files. The Executor runs code/tests. The Critic reviews code BEFORE execution.
- Always include at least one executor subtask after each coder subtask so we exercise the code.
"""


class Orchestrator(Agent):
    name = "orchestrator"
    human_label = "Orchestrator"

    def __init__(self, num_paths: int = 3) -> None:
        super().__init__()
        self._num_paths = num_paths

    def run(self, ctx: AgentContext, **kw: Any) -> dict[str, Any]:
        ctx.bus.emit("agent_started", agent=self.name, label="Tree-of-Thought planning")
        root_id = "orchestrator"
        self.add_graph_node(
            ctx,
            node_id=root_id,
            label=f"🎯 Plan: {ctx.goal[:56]}{'...' if len(ctx.goal) > 56 else ''}",
            agent="orchestrator",
            status="active",
        )

        # 1. ToT generation
        paths_reply = self._llm_chat(
            ctx,
            messages=[
                {"role": "system", "content": ORCH_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({
                        "goal": ctx.goal,
                        "acceptance": ctx.acceptance,
                    }, ensure_ascii=False),
                },
            ],
            stream=False,
        )
        paths = self._parse_paths(paths_reply.thought or "")
        if not paths:
            ctx.bus.emit("error", message="Orchestrator produced no paths")
            self.update_graph_node(ctx, root_id, status="error")
            return fail("no_paths_produced")

        # Show all 3 candidates as graph children.
        for i, p in enumerate(paths):
            self.add_graph_node(
                ctx,
                node_id=f"plan_{p.get('id', i + 1)}",
                label=f"Path {p.get('id', i + 1)} · conf={p.get('confidence', 0):.2f}",
                agent="orchestrator",
                status="candidate",
                parent=root_id,
                meta={"conf": p.get("confidence", 0)},
            )

        # 2. Select the highest-confidence path.
        chosen = max(paths, key=lambda p: float(p.get("confidence", 0.0)))
        ctx.bus.emit(
            "terminal_line",
            text=f"[ORCH] Chose path {chosen.get('id')} conf={chosen.get('confidence', 0):.2f}",
            line_type="success",
        )

        # Highlight chosen path node and dim the others.
        for i, p in enumerate(paths):
            if p is chosen:
                self.update_graph_node(ctx, f"plan_{p.get('id', i + 1)}", status="selected")
            else:
                self.update_graph_node(ctx, f"plan_{p.get('id', i + 1)}", status="rejected")

        # 3. Expand chosen into a crisp subtask list.
        exec_reply = self._llm_chat(
            ctx,
            messages=[
                {"role": "system", "content": EXEC_PLAN_PROMPT.format(chosen=chosen.get("description", ""))},
                {
                    "role": "user",
                    "content": json.dumps({
                        "goal": ctx.goal,
                        "acceptance": ctx.acceptance,
                        "chosen_path_steps": chosen.get("steps", []),
                    }, ensure_ascii=False),
                },
            ],
            stream=False,
        )
        subtasks = self._parse_subtasks(exec_reply.thought or "")

        if not subtasks:
            # Fallback: use the steps already in the chosen path.
            subtasks = [
                {
                    "id": f"S{i+1}", 
                    "desc": s, 
                    "agent": "coder" if i % 2 == 0 else "executor",
                    "model_tier": "coding" if i % 2 == 0 else "fast_eval"
                }
                for i, s in enumerate(chosen.get("steps", []))
            ]
        if not subtasks:
            self.update_graph_node(ctx, root_id, status="error")
            return fail("no_subtasks_produced")

        for s in subtasks:
            sid = str(s.get("id") or f"S{len(subtasks)} ")
            self.add_graph_node(
                ctx,
                node_id=sid,
                label=f"{sid} · {str(s.get('desc'))[:48]}",
                agent=str(s.get("agent", "coder")),
                status="pending",
                parent=f"plan_{chosen.get('id', 1)}",
            )

        ctx.bus.emit("agent_finished", agent=self.name, status="ok")
        self.update_graph_node(ctx, root_id, status="success")
        return ok(
            plan={
                "chosen_path": chosen,
                "all_paths": paths,
                "subtasks": subtasks,
            }
        )

    # ---------- parsing helpers ----------

    def _parse_paths(self, text: str) -> list[dict[str, Any]]:
        # First try direct JSON parse.
        try:
            data = json.loads(self._strip_codefence(text))
            if isinstance(data, dict) and isinstance(data.get("paths"), list):
                return [p for p in data["paths"] if isinstance(p, dict)]
        except Exception:
            pass
        # Then regex-extract a { ... } block.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict) and isinstance(data.get("paths"), list):
                    return list(data["paths"])
            except Exception:
                pass
        return []

    def _parse_subtasks(self, text: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._strip_codefence(text))
            if isinstance(data, dict) and isinstance(data.get("subtasks"), list):
                return list(data["subtasks"])
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict) and isinstance(data.get("subtasks"), list):
                    return list(data["subtasks"])
            except Exception:
                pass
        return []

    @staticmethod
    def _strip_codefence(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s[3:]
            if s.startswith("json"):
                s = s[4:]
        if s.endswith("```"):
            s = s[:-3]
        return s.strip()
