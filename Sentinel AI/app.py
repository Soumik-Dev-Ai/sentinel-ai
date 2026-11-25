"""Sentinel AI 2.0 - Hugging Face Spaces Entrypoint

Provides both an interactive Gradio interface for public testing and mounts
the complete Sentinel AI FastAPI backend (/ws/run, /health, /api/*) for
the decoupled Vercel frontend.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from fastapi.middleware.cors import CORSMiddleware
import gradio as gr
import gradio.routes
import spaces

from backend import config
from backend.llm.router import LLMRouter
from backend.orchestrator.base import EventBus
from backend.orchestrator.escalation import EscalationManager
from backend.orchestrator.pipeline import MultiAgentPipeline
from backend.server.server import app as fastapi_app


@spaces.GPU(duration=60)
def run_sentinel_agent(
    goal: str,
    acceptance_text: str = "",
    max_retries: int = 3,
) -> tuple[str, str, str, str, str, str]:
    """Execute the multi-agent pipeline and return structured results for Gradio."""
    if not goal or not goal.strip():
        return (
            "Please provide a goal.",
            "",
            "",
            "",
            "",
            "Status: Idle - No input provided",
        )

    acceptance = [line.strip() for line in acceptance_text.splitlines() if line.strip()]
    workspace = Path(mkdtemp(prefix="sentinel_space_ws_"))

    terminal_logs: list[str] = []
    tot_plan_lines: list[str] = []
    generated_code: str = ""
    critic_report: str = ""
    exec_report: str = ""

    bus = EventBus()

    def on_event(ev_type: str, data: dict[str, Any]) -> None:
        nonlocal generated_code, critic_report, exec_report
        ts = time.strftime("%H:%M:%S")
        if ev_type == "terminal_line":
            terminal_logs.append(f"[{ts}] {data.get('text', '')}")
        elif ev_type == "agent_started":
            terminal_logs.append(f"[{ts}] ▷ [{data.get('agent', 'system').upper()}] {data.get('label', '')}")
        elif ev_type == "graph_node":
            label = data.get("label", "")
            status = data.get("status", "")
            if "Path P" in label or "Plan:" in label or label.startswith("S"):
                tot_plan_lines.append(f"- **{label}** (`status: {status}`)")
        elif ev_type == "code_written":
            generated_code = data.get("content", "")
        elif ev_type == "critic_verdict":
            scores = data.get("scores", {})
            verdict = data.get("verdict", "UNKNOWN")
            total = scores.get("total", 0)
            critic_report = (
                f"### Verdict: **{verdict}** (Total: {total}/100)\n\n"
                f"- **Correctness:** {scores.get('correctness', 0)}/10\n"
                f"- **Edge Cases:** {scores.get('edge_cases', 0)}/10\n"
                f"- **Acceptance Criteria:** {scores.get('acceptance', 0)}/10\n"
                f"- **Readability:** {scores.get('readability', 0)}/10\n\n"
                f"**Feedback / Issues:** {data.get('issues', 'None')}"
            )
        elif ev_type == "code_executed":
            exit_code = data.get("exit_code", -1)
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            exec_report = (
                f"**Exit Code:** `{exit_code}` "
                f"({'PASS' if exit_code == 0 else 'FAIL'})\n\n"
                f"```text\n--- STDOUT ---\n{stdout}\n\n--- STDERR ---\n{stderr}\n```"
            )

    bus.subscribe("*", on_event)

    router = LLMRouter()
    pipe = MultiAgentPipeline(
        router=router,
        bus=bus,
        escalation=EscalationManager(timeout_seconds=25),
        config={"max_retries_per_subtask": max_retries, "budget": 1000},
    )

    t0 = time.time()
    terminal_logs.append(f"[{time.strftime('%H:%M:%S')}] Sentinel AI 2.0 Pipeline Initialized.")
    terminal_logs.append(f"[{time.strftime('%H:%M:%S')}] Goal: {goal}")

    result = pipe.run(goal=goal, acceptance=acceptance, workspace=workspace)
    elapsed = time.time() - t0

    if not generated_code:
        for fp in workspace.rglob("*"):
            if fp.is_file() and fp.suffix in (".py", ".c", ".cpp", ".rs", ".go", ".js"):
                try:
                    generated_code = fp.read_text(encoding="utf-8", errors="replace")
                    break
                except Exception:
                    pass

    tot_summary = (
        f"### Tree-of-Thought Strategy\n"
        f"**Chosen Path:** `{result.get('chosen_path', 'P1')}` | "
        f"**Subtasks:** `{len(result.get('subtasks', []))}`\n\n"
        + "\n".join(tot_plan_lines[-12:] if tot_plan_lines else ["Direct execution strategy formulated."])
    )

    telemetry = (
        f"⏱️ **Elapsed:** {elapsed:.2f}s | "
        f"✅ **Success:** {result.get('success')} | "
        f"🔄 **Corrections:** {result.get('self_corrections', 0)} | "
        f"⚡ **Steps:** {result.get('steps_taken', 0)}"
    )

    log_output = "\n".join(terminal_logs)
    return (
        tot_summary,
        generated_code or "# No source files generated",
        critic_report or "Review completed without explicit rubric dump.",
        exec_report or "Execution completed.",
        telemetry,
        log_output,
    )


# ------------------------------------------------------------------
# Gradio UI Definition
# ------------------------------------------------------------------

custom_css = """
.container { max-width: 1200px; margin: auto; }
.header-box { text-align: center; margin-bottom: 1.5rem; }
.badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem; font-weight: 600; margin-right: 0.4rem; }
"""

with gr.Blocks(title="Sentinel AI 2.0 — Autonomous Code Platform", css=custom_css) as demo:
    with gr.Column(elem_classes=["container"]):
        gr.Markdown(
            """
            # 🛡️ Sentinel AI 2.0
            ### Autonomous Self-Correcting Multi-Agent Code Generation & Verification Engine
            *Tree-of-Thought Planning · Parallel Dual-Verification (Critic || Executor) · Multi-Tier LLM Router · Polyglot Sandbox*
            """
        )

        with gr.Tabs():
            with gr.TabItem("🚀 Agent Studio"):
                with gr.Row():
                    with gr.Column(scale=5):
                        goal_input = gr.Textbox(
                            label="Goal / Specification",
                            placeholder="e.g. Write a Python function for binary search with comprehensive edge tests and print ALL TESTS PASSED.",
                            lines=3,
                        )
                        acceptance_input = gr.Textbox(
                            label="Acceptance Criteria (Optional, 1 per line)",
                            placeholder="Must handle empty arrays\nMust handle single-element arrays\nAssert exit code is 0",
                            lines=2,
                        )
                        retries_input = gr.Slider(
                            minimum=1,
                            maximum=5,
                            value=3,
                            step=1,
                            label="Max Self-Correction Cycles",
                        )
                        run_btn = gr.Button("⚡ Run Sentinel Agent", variant="primary")

                        gr.Examples(
                            examples=[
                                [
                                    "Write a Python script that implements iterative binary search with 5 edge-case tests and prints ALL TESTS PASSED.",
                                    "Tests must cover empty list and duplicates\nExit code must be 0",
                                ],
                                [
                                    "Write a Python script that calculates factorial of 10 and prints the result.",
                                    "Must print 3628800",
                                ],
                                [
                                    "Write a Python script 'buggy.py' with an intentional off-by-one Fibonacci bug, run tests to detect it, self-correct the logic, and assert fib(10) == 55.",
                                    "Must recover from initial test failure\nExit code must be 0",
                                ],
                            ],
                            inputs=[goal_input, acceptance_input],
                        )

                    with gr.Column(scale=7):
                        telemetry_box = gr.Markdown("### 📊 Telemetry: Idle")

                        with gr.Tabs():
                            with gr.TabItem("💻 Generated Code"):
                                code_output = gr.Code(language="python", label="Source Code")
                            with gr.TabItem("🎯 Tree-of-Thought Plan"):
                                plan_output = gr.Markdown("Plan will appear here.")
                            with gr.TabItem("⚖️ Critic Verdict"):
                                critic_output = gr.Markdown("Critic audit will appear here.")
                            with gr.TabItem("▶️ Sandbox Execution"):
                                exec_output = gr.Markdown("Execution trace will appear here.")
                            with gr.TabItem("📜 Terminal Stream"):
                                logs_output = gr.Textbox(label="Agent Event Stream", lines=12)

                run_btn.click(
                    fn=run_sentinel_agent,
                    inputs=[goal_input, acceptance_input, retries_input],
                    outputs=[
                        plan_output,
                        code_output,
                        critic_output,
                        exec_output,
                        telemetry_box,
                        logs_output,
                    ],
                )

            with gr.TabItem("🔬 Evaluation Lab"):
                gr.Markdown(
                    """
                    ### Evaluation Lab Empirical Benchmarks
                    Evaluated across 24 comparative runs on diverse algorithmic and systems programming tasks:

                    | Architecture Mode | Completion Rate | Avg Elapsed Time | Reflection Cycles |
                    | :--- | :--- | :--- | :--- |
                    | **Baseline (Self-Correction OFF)** | **75.0%** (9/12) | **48.22s** | 0.00 |
                    | **Sentinel 2.0 (Self-Correction ON)** | **100.0%** (12/12) | **79.11s** | **0.67 / task** |
                    
                    *Self-correction elevated completion rate by +25% absolute (+33.3% relative), recovering 100% of broken tasks.*
                    """
                )

            with gr.TabItem("📖 Architecture & API"):
                gr.Markdown(
                    """
                    ### Decoupled Deployment & External Endpoints
                    This Hugging Face Space runs as both a public Gradio application and the backend for the Vercel frontend:
                    
                    - **Health Endpoint:** `GET /health` and `GET /api/health`
                    - **WebSocket Runner:** `wss://soumik041-sentinel-ai.hf.space/ws/run`
                    - **Provider Telemetry:** `GET /api/providers/health`
                    - **Run History:** `GET /api/history`
                    - **Evaluation Suite API:** `POST /api/evaluations/run`
                    """
                )

# Hook into Gradio's internal FastAPI app creation to attach all Sentinel AI backend routes
_orig_create_app = gradio.routes.App.create_app

def _custom_create_app(blocks: gr.Blocks, *args: Any, **kwargs: Any) -> Any:
    app = _orig_create_app(blocks, *args, **kwargs)

    # Attach all Sentinel AI backend routes (/ws/run, /health, /api/*)
    existing_paths = {getattr(r, "path", None) for r in app.routes}
    for route in fastapi_app.routes:
        route_path = getattr(route, "path", None)
        if route_path and route_path not in existing_paths:
            app.routes.insert(0, route)

    return app

gradio.routes.App.create_app = _custom_create_app

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, ssr_mode=False)
