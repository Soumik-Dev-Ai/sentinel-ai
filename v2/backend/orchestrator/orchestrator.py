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


ORCH_SYSTEM_PROMPT = """You are ORCHESTRATOR, the strategic planner of Sentinel AI 2.0.

For any user goal, generate 3 distinct, concise approach paths.

You MUST respond with ONLY a JSON object of this shape (no prose before/after):

{
  "paths": [
    {
      "id": "P1",
      "description": "short description of the approach",
      "steps": ["implement code", "run and verify tests"],
      "confidence": 0.90,
      "rationale": "one-line rationale",
      "risks": []
    },
    {
      "id": "P2",
      "description": "alternate approach",
      "steps": ["implement code", "run and verify tests"],
      "confidence": 0.80,
      "rationale": "one-line rationale",
      "risks": []
    },
    {
      "id": "P3",
      "description": "third approach",
      "steps": ["implement code", "run and verify tests"],
      "confidence": 0.70,
      "rationale": "one-line rationale",
      "risks": []
    }
  ]
}

Rules:
- Keep descriptions and steps brief (1-2 sentences each) to conserve tokens.
- Confidence reflects predicted probability of success (0.0 to 1.0).
- Order by confidence descending.
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
   * `strategic` - High intelligence needed (system architecture, distributed systems, high ambiguity)
   * `coding` - Deep code generation or logic refactoring
   * `fast_eval` - Simple algorithmic tasks (e.g. binary search, sorting, factorial, basic utilities, test runners). Always use `fast_eval` for standard algorithms to conserve tokens and reduce latency.
- Every `coder` subtask is automatically reviewed by Critic and executed by Executor in parallel — do NOT emit separate `critic` or `executor` subtasks.
- Keep the plan minimal (1 `coder` subtask for a single script/algorithm; 2–3 max only for distinct modules). Never split a single file across multiple subtasks.
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
            # Resilient fallback: synthesize direct execution plan instead of crashing
            ctx.bus.emit("terminal_line", text="[ORCH] Notice: Synthesizing direct execution plan from goal", line_type="info")
            paths = [
                {
                    "id": "P1",
                    "description": f"Direct implementation: {ctx.goal[:60]}",
                    "steps": [
                        f"Implement solution: {ctx.goal}",
                        f"Run and verify tests for: {ctx.goal}",
                    ],
                    "confidence": 0.90,
                    "rationale": "Direct execution plan",
                    "risks": [],
                }
            ]

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
        cleaned = self._strip_codefence(text)
        # 1. Direct JSON parse
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                for k in ("paths", "approaches", "options", "plans"):
                    if isinstance(data.get(k), list) and data[k]:
                        return [p for p in data[k] if isinstance(p, dict)]
            elif isinstance(data, list) and data:
                return [p for p in data if isinstance(p, dict)]
        except Exception:
            pass

        # 2. Greedy regex block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    for k in ("paths", "approaches", "options", "plans"):
                        if isinstance(data.get(k), list) and data[k]:
                            return [p for p in data[k] if isinstance(p, dict)]
                elif isinstance(data, list) and data:
                    return [p for p in data if isinstance(p, dict)]
            except Exception:
                pass

        # 3. Individual path object regex extraction (robust to truncated JSON)
        path_objs = []
        for obj_m in re.finditer(r'\{[^{}]*"id"\s*:\s*"(?P<id>P\d+)"[^{}]*"steps"\s*:\s*\[(?P<steps>[^\]]*)\][^{}]*\}', text, re.DOTALL):
            try:
                p_id = obj_m.group("id")
                raw_steps = obj_m.group("steps")
                steps = [s.strip().strip('"').strip("'") for s in raw_steps.split(",") if s.strip()]
                path_objs.append({
                    "id": p_id,
                    "description": f"Approach {p_id}",
                    "steps": steps or ["implement solution", "run tests"],
                    "confidence": 0.85,
                })
            except Exception:
                pass
        if path_objs:
            return path_objs

        return []

    def _parse_subtasks(self, text: str) -> list[dict[str, Any]]:
        cleaned = self._strip_codefence(text)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                for k in ("subtasks", "tasks", "steps"):
                    if isinstance(data.get(k), list) and data[k]:
                        return list(data[k])
            elif isinstance(data, list) and data:
                return list(data)
        except Exception:
            pass

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    for k in ("subtasks", "tasks", "steps"):
                        if isinstance(data.get(k), list) and data[k]:
                            return list(data[k])
                elif isinstance(data, list) and data:
                    return list(data)
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
