"""Coder agent — specialized exclusively in writing clean, runnable Python code.

Driven by RAG memory: before generating code, the coder queries the vector
store for past solutions and error strategies for similar goals/subtasks and
includes them in the system prompt so we benefit from prior experience.

The coder emits graph_node events ("Coder Writing ...") and
agent_stream events for live token streaming in the UI.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from backend.orchestrator.base import Agent, AgentContext, fail, ok


CODER_SYSTEM_PROMPT = """You are CODER, a specialist agent that writes clean, runnable, idiomatic Python 3.12+ code.

You will receive:
- A user goal and acceptance criteria.
- A single subtask to address right now (do not solve everything).
- Optionally, the workspace path to write to.
- (RAG) memories of past similar tasks and error strategies — use them when relevant.

OUTPUT CONTRACT — you must reply with ONLY this JSON object (no prose):

{{
  "rationale": "1-2 sentences explaining the implementation choice",
  "filename": "my_script.py",            // workspace-relative file path
  "language": "python",
  "code": "...",                          // full file content as a string
  "self_check": {{
    "handles_edge_cases": true,
    "covers_acceptance": true
  }}
}}

Rules:
- Output **complete file content** (not a diff). No partial/snippet placeholders.
- Use only standard-library modules unless the goal requires otherwise.
- Include docstrings for public functions + 2-4 inline comments.
- If the subtask cannot be implemented safely, return empty `code` and a non-empty `rationale`.
- Set `filename` to a path-safe snake_case identifier ending in `.py`.
"""


class Coder(Agent):
    name = "coder"
    human_label = "Coder"

    def run(self, ctx: AgentContext, **kw: Any) -> dict[str, Any]:
        subtask_desc = kw.get("subtask_desc") or ctx.subtask_desc or ctx.goal
        prior_failures = kw.get("prior_failures", [])  # list of dict {stderr, suggestion}
        file_hint = kw.get("filename_hint") or "main.py"

        node_id = kw.get("node_id") or f"coder_{int(time.time() * 1000)}"
        ctx.bus.emit("agent_started", agent=self.name, label=f"Writing: {subtask_desc[:50]}")
        self.add_graph_node(
            ctx,
            node_id=node_id,
            label=f"💻 {subtask_desc[:48]}",
            agent="coder",
            status="active",
            parent=kw.get("parent_node"),
        )

        # ---- RAG recall ----
        rag_query = f"{ctx.goal} {subtask_desc}"
        recall = ctx.memory.format_preamble_for_coder(rag_query)
        if recall:
            ctx.bus.emit("memory_recall", query=rag_query, n=len(ctx.memory.all_entries()))
            ctx.bus.emit("terminal_line", text=f"[CODER] RAG retrieved:\n{recall}", line_type="success")

        # ---- prompt ----
        user_payload: dict[str, Any] = {
            "goal": ctx.goal,
            "acceptance": ctx.acceptance,
            "subtask": subtask_desc,
            "filename_hint": file_hint,
        }
        if recall:
            user_payload["past_learnings"] = recall
        if prior_failures:
            user_payload["recent_failures"] = prior_failures[-2:]

        reply = self._llm_chat(
            ctx,
            messages=[
                {"role": "system", "content": CODER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            stream=True,
        )

        parsed = self._parse_coder_reply(reply.thought or "")
        if not parsed:
            self.update_graph_node(ctx, node_id, status="error")
            ctx.bus.emit("error", message="Coder produced unparseable output")
            return fail("unparseable_output")

        filename = str(parsed.get("filename") or file_hint).strip() or file_hint
        code = str(parsed.get("code") or "")
        rationale = str(parsed.get("rationale") or "")

        if not code.strip():
            self.update_graph_node(ctx, node_id, status="error")
            ctx.bus.emit("terminal_line", text="[CODER] No code generated.", line_type="error")
            return fail("empty_code", rationale=rationale)

        # Write the file to the workspace via the existing WriteFileTool so path
        # sandboxing & telemetry path-or-traversal safety is enforced.
        from backend.tools.file_io import WriteFileTool

        tool = WriteFileTool(workspace=ctx.workspace)
        result = tool.invoke({"path": filename, "content": code})
        if not result.get("ok"):
            self.update_graph_node(ctx, node_id, status="error")
            return fail("write_failed", details=result)

        ctx.path_to_file = filename
        ctx.bus.emit("code_written", path=filename, content=code)
        ctx.bus.emit(
            "terminal_line",
            text=f"[CODER] Wrote {filename} ({len(code)} bytes): {rationale}",
            line_type="success",
        )

        self.update_graph_node(ctx, node_id, status="success")
        ctx.bus.emit("agent_finished", agent=self.name, status="ok")

        return ok(
            filename=filename,
            code=code,
            rationale=rationale,
            node_id=node_id,
        )

    # ---------- parser ----------

    def _parse_coder_reply(self, text: str) -> Optional[dict[str, Any]]:
        # try direct JSON
        s = self._strip_fence(text)
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
        # aggressive fallback: if the LLM outputted broken JSON with literal newlines in the "code" field, extract it
        code_m = re.search(r'"code":\s*"(.*?)"\s*(?:,\s*"self_check"|\}$)', text, re.DOTALL)
        if code_m:
            raw_code = code_m.group(1)
            # LLMs sometimes escape quotes or newlines inconsistently when they break JSON formatting
            raw_code = raw_code.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            
            # Extract filename if possible
            filename_m = re.search(r'"filename":\s*"([^"]+)"', text)
            fname = filename_m.group(1) if filename_m else "generated.py"
            
            return {
                "rationale": "Extracted via broken JSON regex fallback",
                "filename": fname,
                "language": "python",
                "code": raw_code,
                "self_check": {"handles_edge_cases": True, "covers_acceptance": True},
            }
        
        # secondary regex fallback: extract code from markdown python block if they just ignored JSON
        code_m = re.search(r"(?s)```python\n(.*?)\n```", text)
        if code_m:
            return {
                "rationale": "Extracted via markdown regex fallback",
                "filename": "generated.py",
                "language": "python",
                "code": code_m.group(1),
                "self_check": {"handles_edge_cases": True, "covers_acceptance": True},
            }
        return None

    @staticmethod
    def _strip_fence(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s[3:]
            if s.startswith("json"):
                s = s[4:]
        if s.endswith("```"):
            s = s[:-3]
        return s.strip()
