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


CODER_SYSTEM_PROMPT = """You are CODER, a specialist agent that writes clean, runnable, idiomatic code across Python, C, C++, Rust, Go, or JavaScript.

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
- Set `filename` and `language` matching the target language (e.g. `main.c` / `c`, `main.cpp` / `cpp`, `main.rs` / `rust`, `main.go` / `go`, `main.js` / `javascript`, or `.py` / `python`). Default to python if unspecified.
- For compiled languages (C, C++, Rust, Go): include complete headers/imports, check NULL on allocations, free heap memory, and provide a self-contained `main()` test harness with assertions exiting 0 on success.
- Do NOT use banned safety patterns (`subprocess`, `os.system`, `os.remove`, `os.rmdir`, `shutil.rmtree`, `__import__`, `ctypes`, `socket`, `multiprocessing`, `signal`). To execute another `.py` file, import it or use `runpy.run_path`.
- If `recent_failures` is provided (self-correction retry), fix the root cause so the script runs cleanly and exits with code 0 (e.g. if an input file like `data.csv`, `essay.txt`, or `users.json` is missing, generate a valid sample file automatically if `not os.path.exists(...)`; if a prior attempt had an intentional error that the goal asked to observe first and then fix, output the FIXED working code now).
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
            ctx.bus.emit(
                "terminal_line",
                text=f"[CODER] Attempt {attempt} unparseable; triggering self-correction retry...",
                line_type="recovery",
            )
            return fail("unparseable_output")

        filename = str(parsed.get("filename") or file_hint).strip() or file_hint
        code = str(parsed.get("code") or "")
        rationale = str(parsed.get("rationale") or "")
        if "\\n" in code:
            try:
                import ast
                ast.parse(code)
            except SyntaxError:
                fixed = code.replace("\\\n", "\n").replace("\\n", "\n").replace('\"', '"').replace("\'", "'")
                try:
                    ast.parse(fixed)
                    code = fixed
                except SyntaxError:
                    pass

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

    @staticmethod
    def _infer_fname_lang(detected_tag: str, code_body: str) -> tuple[str, str]:
        ext_map = {
            "c": (".c", "c"), "cpp": (".cpp", "cpp"), "c++": (".cpp", "cpp"),
            "rust": (".rs", "rust"), "rs": (".rs", "rust"),
            "go": (".go", "go"), "golang": (".go", "go"),
            "javascript": (".js", "javascript"), "js": (".js", "javascript"),
            "node": (".js", "javascript"), "python": (".py", "python"), "py": (".py", "python"),
        }
        if detected_tag in ext_map:
            ext, lang = ext_map[detected_tag]
            return f"main{ext}", lang
        if "#include" in code_body:
            return "main.c", "c"
        if "package main" in code_body:
            return "main.go", "go"
        if "fn main" in code_body:
            return "main.rs", "rust"
        return "main.py", "python"

    def _parse_coder_reply(self, text: str) -> Optional[dict[str, Any]]:
        if not text:
            return None
        # 1. try direct JSON
        s = self._strip_fence(text)
        try:
            candidate = json.loads(s)
            if isinstance(candidate, dict) and "code" in candidate:
                return candidate
        except Exception:
            pass
        # 2. search for outer { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                candidate = json.loads(m.group(0))
                if isinstance(candidate, dict) and "code" in candidate:
                    return candidate
            except Exception:
                pass
        # 3. aggressive fallback: broken JSON with unescaped newlines in "code"
        code_m = re.search(r'"code"\s*:\s*"(.*?)"\s*(?:,\s*"(?:self_check|rationale|filename|language)"|\s*\})', s, re.DOTALL)
        if code_m:
            raw_code = code_m.group(1)
            raw_code = raw_code.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            filename_m = re.search(r'"filename"\s*:\s*"([^"]+)"', s)
            fname = filename_m.group(1) if filename_m else "main.py"
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "py"
            _, lang = self._infer_fname_lang(ext, raw_code)
            return {
                "rationale": "Extracted via broken JSON regex fallback",
                "filename": fname,
                "language": lang,
                "code": raw_code,
                "self_check": {"handles_edge_cases": True, "covers_acceptance": True},
            }
        
        # 4. JSON with markdown code block inside "code": ```lang ... ```
        inside_fence = re.search(r'"code"\s*:\s*```(?P<lang>[a-zA-Z0-9_\+\-]+)?\s*\n(?P<code>.*?)\n```', text, re.DOTALL)
        if inside_fence:
            code_body = inside_fence.group("code")
            detected_tag = (inside_fence.group("lang") or "").lower()
            fname, lang = self._infer_fname_lang(detected_tag, code_body)
            return {
                "rationale": "Extracted from markdown-in-json fence",
                "filename": fname,
                "language": lang,
                "code": code_body,
                "self_check": {"handles_edge_cases": True, "covers_acceptance": True},
            }

        # 5. secondary regex fallback: extract code from markdown block for any language
        poly_m = re.search(r"(?s)```(?P<lang>[a-zA-Z0-9_\+\-]+)?\s*\n(?P<code>.*?)\n```", text)
        if poly_m:
            detected_tag = (poly_m.group("lang") or "").lower()
            code_body = poly_m.group("code")
            fname, lang = self._infer_fname_lang(detected_tag, code_body)
            return {
                "rationale": "Extracted via markdown regex fallback",
                "filename": fname,
                "language": lang,
                "code": code_body,
                "self_check": {"handles_edge_cases": True, "covers_acceptance": True},
            }

        # 6. Raw code fallback if LLM omitted markdown fences
        for kw in ("def ", "import ", "#include", "package main", "fn main", "function ", "class "):
            if kw in text:
                fname, lang = self._infer_fname_lang("", text)
                return {
                    "rationale": "Extracted raw code",
                    "filename": fname,
                    "language": lang,
                    "code": text.strip(),
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
