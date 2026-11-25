"""MultiAgentPipeline — Sentinel AI 2.0 master orchestrator.

Wires together:
    - Orchestrator (Tree-of-Thought planning)
    - Coder (writes code)
    - Critic (LLM-as-a-Judge, must score >= 8/10 before execution)
    - Executor (runs the code)
    - RetryRouter (adaptive: syntax -> line_patch, logic -> rewrite, external -> backoff)
    - EscalationManager (human-in-the-loop after 2 retries @ conf < 0.5)
    - VectorStore (RAG memory persisted on disk)
    - CostTracker (token + USD budget telemetry)

Pipeline pseudocode per subtask:

    plan = Orchestrator.run(goal)         # ToT -> 3 paths -> 1 -> subtasks
    for subtask in plan.subtasks:
        for retry in range(max_retries_per_subtask):
            code = Coder.run(subtask, prior_failures=...)

            critique = Critic.run(code)
            if not critique.passes:
                # rejected by judge — counts as a self-correction
                record_attempt(subtask, confidence = critique.total / 100)
                if escalation.should_escalate(subtask):
                    question = build_clarifying_question(subtask, critique)
                    escalation.request(ctx, subtask, question)
                    answer = escalation.wait_until_answer(...)
                    if answer is None:
                        mark_unresolvable; continue outer loop
                    append answer to prior_failures; continue
                else:
                    prior_failures.append(critique.as_failure())
                    continue retry loop

            exec_result = Executor.run(code)
            if exec_result.success:
                memory.add(kind="solved", goal=..., summary=..., strategy=...)
                break

            failure = classify(exec_result)
            strategy = RetryRouter.next_strategy(subtask, failure)
            emit retry_strategy
            if strategy.wait_seconds > 0:
                time.sleep(strategy.wait_seconds)
            record_attempt(subtask, confidence=1.0 - severity_score(failure))
            if escalation.should_escalate(subtask):
                escalation.request(...)
                ...
            prior_failures.append(strategy.as_failure())
        else:
            memory.add(kind="error", goal=..., strategy=...,
                       error_signature=...)

The pipeline is the single blocking function called by the FastAPI server.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Optional

from backend.llm.router import LLMRouter
from backend.memory.vector_store import VectorStore, error_signature
from backend.orchestrator.base import AgentContext, EventBus, fail
from backend.orchestrator.coder import Coder
from backend.orchestrator.cost import CostTracker, TokenBudget
from backend.orchestrator.critic import Critic
from backend.orchestrator.escalation import EscalationManager
from backend.orchestrator.executor import Executor
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.retry import Failure, FailureCategory, RetryRouter, Strategy


PIPELINE_DEFAULTS = {
    "max_retries_per_subtask": 3,
    "telemetry_emit_interval_seconds": 1.0,
    "max_total_cost_usd": 5.0,
    "max_total_tokens": 200_000,
}


class MultiAgentPipeline:
    """The blocking pipeline the WebSocket server invokes in a worker thread."""

    def __init__(
        self,
        router: Optional[LLMRouter] = None,
        memory: Optional[VectorStore] = None,
        bus: Optional[EventBus] = None,
        cost: Optional[CostTracker] = None,
        escalation: Optional[EscalationManager] = None,
        retry: Optional[RetryRouter] = None,
        orchestrator: Optional[Orchestrator] = None,
        coder: Optional[Coder] = None,
        critic: Optional[Critic] = None,
        executor: Optional[Executor] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.memory = memory or VectorStore(
            persist_dir=Path.home() / ".sentinel_ai" / "memory",
        )
        self.cost = cost or CostTracker(
            budget=TokenBudget(
                max_total_cost_usd=PIPELINE_DEFAULTS["max_total_cost_usd"],
                max_total_tokens=PIPELINE_DEFAULTS["max_total_tokens"],
            ),
            on_record=lambda rec: self.bus.emit(
                "telemetry_update", **self.cost.snapshot()
            ),
        )
        self.router = router or LLMRouter()
        self.escalation = escalation or EscalationManager()
        self.retry = retry or RetryRouter()
        self.orchestrator = orchestrator or Orchestrator()
        self.coder = coder or Coder()
        self.critic = critic or Critic()
        self.executor = executor or Executor()
        self._cfg = {**PIPELINE_DEFAULTS, **(config or {})}

    @property
    def active_escalation(self) -> EscalationManager:
        """The escalation manager this pipeline is using.
        The WebSocket server should route escalation answers here, not
        to the module-level global singleton."""
        return self.escalation

    # ----------------------------------------------------------------

    def run(
        self,
        goal: str,
        acceptance: Optional[list[str]] = None,
        workspace: Optional[Path] = None,
        input_text: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Main entry point -- blocks until pipeline is done."""
        run_id = run_id or uuid.uuid4().hex[:12]
        if acceptance is None:
            acceptance = []
        if workspace is None:
            import tempfile
            workspace = Path(tempfile.mkdtemp(prefix="agent_ws_"))
        workspace.mkdir(parents=True, exist_ok=True)
        ctx = AgentContext(
            goal=goal,
            acceptance=acceptance,
            workspace=workspace,
            router=self.router,
            bus=self.bus,
            cost=self.cost,
            memory=self.memory,
            run_id=run_id,
        )
        # Emit initial telemetry snapshot so UI shows zeroed counters immediately.
        self.bus.emit("telemetry_update", **self.cost.snapshot())

        ctx.bus.emit(
            "terminal_line",
            text=(
                f"[SENTINEL 2.0] Starting multi-agent run id={run_id}\n"
                f"  goal: {goal}\n  acceptance: {acceptance or '—'}\n"
                f"  memory: {self.memory.count()} entries  workspace: {workspace}"
            ),
            line_type="step",
        )

        # If input text provided, drop it into the workspace for any reads.
        if input_text:
            try:
                (Path(workspace) / "input.txt").write_text(input_text, encoding="utf-8")
            except Exception:
                pass

        # ----- 1. Planning via Tree-of-Thought -----
        ctx.subtask_desc = "plan"
        ctx.subtask_id = "S0"
        plan_result = self.orchestrator.run(ctx)
        if not plan_result["ok"]:
            ctx.bus.emit("completed",
                         result=self._final_result(
                             success=False, goal=goal,
                             final_output="Orchestrator failed to plan.",
                             metrics=self._summary_metrics(ctx, elapsed=0.0),
                         ))
            return self._final_result(False, goal, "Orchestrator failed to plan.",
                                       self._summary_metrics(ctx, 0.0))

        plan = plan_result["plan"]
        subtasks = plan["subtasks"]
        ctx.bus.emit(
            "terminal_line",
            text=(
                f"[ORCH] Plan: chosen_path='{plan['chosen_path'].get('id')}' "
                f"| subtasks={len(subtasks)}"
            ),
            line_type="success",
        )

        # ----- 2. Drive subtasks through the agent stack with ToT fallback -----
        all_paths = sorted(
            plan.get("all_paths", []),
            key=lambda p: float(p.get("confidence", 0.0)),
            reverse=True,
        )
        attempted_path_ids: set[str] = set()
        plan_chosen_path = plan.get("chosen_path", {})
        if plan_chosen_path.get("id"):
            attempted_path_ids.add(str(plan_chosen_path["id"]))

        per_subtask_outputs: list[dict[str, Any]] = []
        overall_start = time.time()
        aborted = False

        current_subtasks = subtasks
        while True:
            outputs, aborted = self._execute_subtasks(
                ctx, plan, current_subtasks, workspace, goal, overall_start,
            )
            if outputs:
                per_subtask_outputs = outputs

            success_count = sum(
                1 for s in per_subtask_outputs if s.get("resolved")
            )
            success = (success_count == len(per_subtask_outputs)) and not aborted

            if success or aborted:
                break

            # -- ToT fallback: try the next-highest-scoring path --
            remaining = [
                p for p in all_paths
                if str(p.get("id", "")) not in attempted_path_ids
                and p.get("steps")
            ]
            if not remaining:
                break

            next_path = remaining[0]
            attempted_path_ids.add(str(next_path["id"]))
            current_subtasks = [
                {"id": f"F{i+1}", "desc": s,
                 "agent": "coder" if i % 2 == 0 else "executor"}
                for i, s in enumerate(next_path.get("steps", []))
            ]
            plan["chosen_path"] = next_path
            plan["subtasks"] = current_subtasks

            ctx.bus.emit(
                "terminal_line",
                text=(
                    f"[ORCH] Path '{plan_chosen_path.get('id')}' failed — "
                    f"falling back to '{next_path.get('id')}' "
                    f"(conf={next_path.get('confidence')})"
                ),
                line_type="recovery",
            )
            ctx.bus.emit(
                "graph_node",
                id=f"fallback_{next_path.get('id')}",
                label=f"🔄 Fallback: {next_path.get('id')}",
                status="active",
            )

            per_subtask_outputs = []  # start fresh for the fallback path

        # ----- 3. Wrap up -----
        elapsed = round(time.time() - overall_start, 2)
        success_count = sum(
            1 for s in per_subtask_outputs if s.get("resolved")
        )
        success = (success_count == len(per_subtask_outputs)) and not aborted

        final_output = self._compose_final_output(
            goal, per_subtask_outputs, plan, workspace=workspace,
        )

        generated_code: dict[str, str] = {}
        polyglot_exts = {".py", ".go", ".rs", ".c", ".cpp", ".cc", ".cxx", ".js", ".mjs", ".ts", ".sh"}
        for f in sorted(Path(workspace).iterdir()):
            if f.is_file() and f.suffix.lower() in polyglot_exts:
                try:
                    generated_code[f.name] = f.read_text(encoding="utf-8")
                except Exception:
                    pass

        ctx.bus.emit("telemetry_update", **self.cost.snapshot())
        metrics = self._summary_metrics(ctx, elapsed)
        result = self._final_result(
            success=success,
            goal=goal,
            final_output=final_output,
            metrics=metrics,
            subtasks=per_subtask_outputs,
            plan=plan,
            generated_code=generated_code,
        )
        ctx.bus.emit(
            "terminal_line",
            text=(
                f"[SENTINEL 2.0] Run finished: success={success}\n"
                f"  subtasks_resolved={success_count}/{len(per_subtask_outputs)}\n"
                f"  elapsed={elapsed}s  tokens={metrics['tokens_total']}\n"
                f"  cost=${metrics['cost_total_usd']}"
            ),
            line_type="complete",
        )
        ctx.bus.emit("completed", result=result)

        # Persist to SQLite history
        try:
            from backend.db.store import insert_run
            insert_run(
                run_id=run_id,
                goal=goal,
                success=success,
                steps=len(per_subtask_outputs),
                corrections=result.get("self_corrections", 0),
                elapsed=elapsed,
                provider=self.router.last_successful_provider,
                tokens=metrics.get("tokens_total", 0),
                cost=metrics.get("cost_total_usd", 0.0),
                metadata={"plan_path": plan.get("chosen_path", {}).get("id", "")},
            )
        except Exception:
            pass  # DB failure must not crash the pipeline

        return result

    # ----------------------------------------------------------------
    # Subtask execution (extracted so the ToT fallback loop can re-drive it)
    # ----------------------------------------------------------------

    def _execute_subtasks(
        self,
        ctx: AgentContext,
        plan: dict[str, Any],
        subtasks: list[dict[str, Any]],
        workspace: Path,
        goal: str,
        overall_start: float,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Execute all subtasks in *subtasks*; returns (per_subtask_outputs, aborted)."""
        per_subtask_outputs: list[dict[str, Any]] = []
        aborted = False

        for idx, subtask in enumerate(subtasks):
            subtask_id = str(subtask.get("id") or f"S{idx + 1}")
            subtask_desc = str(subtask.get("desc") or "")
            subtask_agent_kind = str(subtask.get("agent") or "coder").lower()

            ctx.subtask_id = subtask_id
            ctx.subtask_desc = subtask_desc
            ctx.model_tier = subtask.get("model_tier", "strategic")

            self.retry.reset(subtask_id)
            self.escalation.reset(subtask_id)

            ctx.bus.emit(
                "terminal_line",
                text=f"[ORCH] === Begin subtask {subtask_id} ({subtask_agent_kind}): {subtask_desc}",
                line_type="step",
            )
            self._update_graph_node(ctx, subtask_id, status="active")

            if subtask_agent_kind == "executor":
                target_file = self._latest_file_in_workspace(workspace) or "main.py"
                exec_outcome = self.executor.run(
                    ctx,
                    filename=target_file,
                    test_mode=bool(subtask.get("test_mode", False)),
                    test_path=subtask.get("test_path"),
                    parent_node=subtask_id,
                    node_id=f"{subtask_id}_exec",
                )
                executor_resolved = bool(
                    exec_outcome.get("ok") and exec_outcome.get("success")
                )
                per_subtask_outputs.append({
                    "subtask_id": subtask_id,
                    "agent": "executor",
                    "resolved": executor_resolved,
                    "outcome": exec_outcome,
                    "attempts": 1,
                })
                self._mark_subtask_status(
                    ctx, subtask_id, subtask_agent_kind,
                    ok=executor_resolved,
                )
                if not executor_resolved:
                    self.memory.add(
                        kind="error",
                        goal=goal,
                        summary=subtask_desc,
                        error_signature="ExecutionFailure",
                        strategy="revisit code in prior subtask",
                        success=False,
                        metadata={"subtask_id": subtask_id},
                    )
                else:
                    self.memory.add(
                        kind="solved",
                        goal=goal,
                        summary=subtask_desc,
                        error_signature=None,
                        strategy=None,
                        success=True,
                        metadata={"subtask_id": subtask_id, "filename": target_file},
                    )
                    ctx.bus.emit("memory_stored", kind="solved", subtask_id=subtask_id, filename=target_file)
                continue

            # ---- coder/critic/executor trial loop ----
            prior_failures: list[dict[str, Any]] = []
            attempt = 0
            resolved = False
            success_outcome: Optional[dict[str, Any]] = None

            max_retries = int(self._cfg["max_retries_per_subtask"])
            while attempt < max_retries:
                attempt += 1
                snap = self.cost.snapshot()
                if snap.get("budget_exhausted"):
                    ctx.bus.emit(
                        "terminal_line",
                        text=f"[BUDGET] {snap.get('budget_reason')}; aborting {subtask_id}",
                        line_type="error",
                    )
                    aborted = True
                    break

                # --- Coder ---
                coder_node = f"{subtask_id}_coder_{attempt}"
                coder_outcome = self.coder.run(
                    ctx,
                    subtask_desc=subtask_desc,
                    filename_hint=subtask.get("filename") or self._infer_filename_hint(subtask_desc, goal),
                    prior_failures=prior_failures,
                    parent_node=subtask_id,
                    node_id=coder_node,
                )
                if not coder_outcome.get("ok"):
                    prior_failures.append({
                        "stderr": "Coder produced no usable code.",
                        "suggestion": "Try again.",
                    })
                    self.escalation.record_attempt(subtask_id, confidence=0.3)
                    if self._maybe_escalate(ctx, subtask_id, subtask_desc, prior_failures):
                        continue
                    continue

                filename = coder_outcome["filename"]
                code = coder_outcome["code"]

                # --- Critic ---
                critic_node = f"{subtask_id}_critic_{attempt}"
                critic_outcome = self.critic.run(
                    ctx,
                    filename=filename,
                    code=code,
                    prior_issues=[f for pf in prior_failures for f in ([pf] if isinstance(pf, str) else pf.get("issues", []))],
                    parent_node=subtask_id,
                    node_id=critic_node,
                )
                if not critic_outcome.get("ok"):
                    pass
                elif not critic_outcome.get("passes"):
                    conf = max(0.05, (critic_outcome.get("total", 0) or 0) / 100.0)
                    self.escalation.record_attempt(subtask_id, confidence=conf)
                    prior_failures.append({
                        "kind": "critic_rejected",
                        "issues": critic_outcome.get("issues", []),
                        "suggestions": critic_outcome.get("fix_suggestions", []),
                        "stderr": "",
                    })
                    ctx.bus.emit(
                        "terminal_line",
                        text=(
                            f"[CRITIC] REJECT total={critic_outcome.get('total', 0)} — "
                            f"sending back to coder (attempt {attempt})"
                        ),
                        line_type="recovery",
                    )
                    if self._maybe_escalate(ctx, subtask_id, subtask_desc, prior_failures):
                        continue
                    continue

                # --- Executor ---
                exec_node = f"{subtask_id}_exec_{attempt}"
                exec_outcome = self.executor.run(
                    ctx,
                    filename=filename,
                    parent_node=subtask_id,
                    node_id=exec_node,
                )
                boolean_success = bool(
                    exec_outcome.get("ok") and exec_outcome.get("success")
                )
                if boolean_success:
                    self.escalation.record_attempt(subtask_id, confidence=0.95)
                    success_outcome = exec_outcome
                    resolved = True
                    self.memory.add(
                        kind="solved",
                        goal=goal,
                        summary=subtask_desc,
                        error_signature=None,
                        strategy=None,
                        success=True,
                        metadata={"subtask_id": subtask_id, "filename": filename},
                    )
                    ctx.bus.emit("memory_stored", kind="solved", subtask_id=subtask_id, filename=filename)
                    break

                failure = self.retry_router_classify(exec_outcome)
                strategy_result = self.retry.next_strategy(
                    subtask_id=subtask_id,
                    failure=failure,
                )
                ctx.bus.emit(
                    "retry_strategy",
                    subtask_id=subtask_id,
                    category=strategy_result.failure.category.value,
                    exception=strategy_result.failure.exception,
                    strategy=strategy_result.strategy.value,
                    attempt=attempt,
                    wait_seconds=strategy_result.wait_seconds,
                    guidance=strategy_result.guidance,
                )
                if strategy_result.wait_seconds > 0:
                    ctx.bus.emit(
                        "terminal_line",
                        text=(
                            f"[BACKOFF] Waiting {strategy_result.wait_seconds:.2f}s "
                            f"before retry (attempt {attempt})"
                        ),
                        line_type="recovery",
                    )
                    time.sleep(min(strategy_result.wait_seconds, 30.0))

                conf = 1.0 - min(1.0, 0.4 + 0.2 * attempt)
                self.escalation.record_attempt(subtask_id, confidence=conf)
                prior_failures.append({
                    "kind": strategy_result.failure.category.value,
                    "exception": strategy_result.failure.exception,
                    "line": strategy_result.failure.line,
                    "stderr": strategy_result.failure.stderr[:1500],
                    "suggestion": strategy_result.guidance,
                })

                self.memory.add(
                    kind="error",
                    goal=goal,
                    summary=subtask_desc,
                    error_signature=error_signature(strategy_result.failure.stderr)[:80],
                    strategy=strategy_result.guidance,
                    success=False,
                    metadata={
                        "subtask_id": subtask_id, "attempt": attempt,
                        "category": strategy_result.failure.category.value,
                    },
                )
                ctx.bus.emit("memory_stored", kind="error", subtask_id=subtask_id)

                if self._maybe_escalate(ctx, subtask_id, subtask_desc, prior_failures):
                    continue
            # end retry-loop

            per_subtask_outputs.append({
                "subtask_id": subtask_id,
                "agent": subtask_agent_kind,
                "resolved": resolved,
                "outcome": success_outcome,
                "attempts": attempt,
            })
            if not resolved:
                ctx.bus.emit(
                    "terminal_line",
                    text=(
                        f"[ORCH] Subtask {subtask_id} not resolved after "
                        f"{attempt} attempts — falling back to next path"
                    ),
                    line_type="error",
                )
            self._mark_subtask_status(
                ctx, subtask_id, subtask_agent_kind, ok=resolved,
            )
            if aborted:
                break

        return per_subtask_outputs, aborted

    # ----------------------------------------------------------------

    def _maybe_escalate(
        self,
        ctx: AgentContext,
        subtask_id: str,
        subtask_desc: str,
        prior_failures: list[dict[str, Any]],
    ) -> bool:
        """If escalation fires AND human answers, append the hint and return True.
        Returns False if no escalation occurred or human timed out / refused.
        """
        if not self.escalation.should_escalate(subtask_id):
            return False
        question = self._build_clarifying_question(
            subtask_id, subtask_desc, prior_failures
        )
        ctx_summary = {
            "subtask_desc": subtask_desc,
            "goal": ctx.goal,
            "attempts": self.escalation.attempts(subtask_id),
            "confidence": self.escalation.average_confidence(subtask_id),
            "prior_failures": prior_failures[-2:],
        }
        esc = self.escalation.request(ctx, subtask_id, question, ctx_summary)
        answer = self.escalation.wait_until_answer(esc)
        if answer is None:
            ctx.bus.emit(
                "terminal_line",
                text=f"[ESCALATE] No human answer within timeout for {subtask_id} — aborting",
                line_type="error",
            )
            return False
        ctx.bus.emit(
            "resume_from_human",
            escalation_id=esc.id,
            subtask_id=subtask_id,
            answer=answer,
        )
        prior_failures.append({
            "kind": "human_hint",
            "suggestion": answer,
            "stderr": "",
        })
        # Reset attempt counter so the retry budget restarts with the hint in hand.
        self.escalation.reset(subtask_id)
        return True

    @staticmethod
    def _build_clarifying_question(
        subtask_id: str,
        subtask_desc: str,
        prior_failures: list[dict[str, Any]],
    ) -> str:
        recent = prior_failures[-2:] if prior_failures else []
        failure_text = "\n".join(
            f"  - {pf.get('kind', '?')}: {pf.get('suggestion', pf.get('stderr', ''))[:160]}"
            for pf in recent
        )
        return (
            f"Subtask {subtask_id!r} stuck after {len(prior_failures)} self-corrections. "
            f"Description: {subtask_desc}\n"
            f"Recent failures:\n{failure_text}\n"
            "Question for you: What requirement or constraint am I missing? "
            "(Answer briefly; the coder will use your hint verbatim.)"
        )

    def _mark_subtask_status(
        self,
        ctx: AgentContext,
        subtask_id: str,
        agent: str,
        ok: bool,
    ) -> None:
        self._update_graph_node(
            ctx, subtask_id, status="success" if ok else "rejected",
        )

    @staticmethod
    def _update_graph_node(
        ctx: AgentContext,
        node_id: str,
        status: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        payload: dict[str, Any] = {"id": node_id, "status": status}
        if meta is not None:
            payload["meta"] = meta
        ctx.bus.emit("graph_node", **payload)

    def _summary_metrics(self, ctx: AgentContext, elapsed: float) -> dict[str, Any]:
        snap = self.cost.snapshot()
        return {
            "elapsed_seconds": elapsed,
            "tokens_input": snap["total_input_tokens"],
            "tokens_output": snap["total_output_tokens"],
            "tokens_total": snap["total_tokens"],
            "cost_total_usd": snap["total_cost_usd"],
            "calls": snap["calls"],
            "budget_remaining_tokens": snap["budget_remaining_tokens"],
            "budget_remaining_usd": snap["budget_remaining_usd"],
            "per_agent": snap["per_agent"],
            "provider_switches": len(self.router.provider_events),
            "memory_entries": self.memory.count(),
        }

    @staticmethod
    def _final_result(
        success: bool,
        goal: str,
        final_output: str,
        metrics: dict[str, Any],
        subtasks: Optional[list[dict[str, Any]]] = None,
        plan: Optional[dict[str, Any]] = None,
        generated_code: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        return {
            "success": success,
            "goal": goal,
            "final_output": final_output,
            "metrics": metrics,
            "subtasks": subtasks or [],
            "plan": plan or {},
            "steps_taken": len(subtasks or []),
            "self_corrections": sum(
                max(0, s.get("attempts", 1) - 1) for s in (subtasks or [])
            ),
            "errors": [],
            "terminal_logs": [],
            "generated_code": generated_code or {},
        }

    @staticmethod
    def _compose_final_output(
        goal: str,
        subtask_outputs: list[dict[str, Any]],
        plan: dict[str, Any],
        workspace: Optional[Path] = None,
    ) -> str:
        lines: list[str] = []
        lines.append("Sentinel AI 2.0 — Multi-Agent Run Report")
        lines.append("=" * 60)
        lines.append(f"Goal: {goal}")
        chosen = plan.get("chosen_path", {})
        lines.append(f"Chosen plan: {chosen.get('id', '?')} (confidence={chosen.get('confidence', '?')})")
        lines.append("")
        lines.append("Subtasks:")
        for s in subtask_outputs:
            sid = s.get("subtask_id", "?")
            agent = s.get("agent", "?")
            resolved = s.get("resolved")
            attempts = s.get("attempts", 0)
            symbol = "[OK]   " if resolved else "[FAIL] "
            lines.append(
                f"  {symbol}{sid} ({agent}) attempts={attempts}:"
            )
            outcome = s.get("outcome")
            if outcome and isinstance(outcome, dict):
                if outcome.get("filename"):
                    lines.append(f"        file: {outcome.get('filename')}")
                if outcome.get("stdout"):
                    lines.append(f"        stdout preview: {str(outcome['stdout'])[:120]}")
                if outcome.get("stderr"):
                    lines.append(f"        stderr preview: {str(outcome['stderr'])[:120]}")
        # attach generated code from disk
        polyglot_exts = {".py", ".go", ".rs", ".c", ".cpp", ".cc", ".cxx", ".js", ".mjs", ".ts", ".sh"}
        if workspace:
            source_files = sorted(p for p in Path(workspace).iterdir() if p.is_file() and p.suffix.lower() in polyglot_exts)
            if source_files:
                lines.append("")
                lines.append("Generated Code:")
                lines.append("-" * 60)
                for sf in source_files:
                    try:
                        code = sf.read_text(encoding="utf-8")
                        lang = sf.suffix.lstrip(".").lower()
                        lang_tag = {"py": "python", "rs": "rust", "js": "javascript", "ts": "typescript"}.get(lang, lang)
                        lines.append(f"\n#### {sf.name}\n```{lang_tag}\n{code}\n```")
                    except Exception:
                        pass
        return "\n".join(lines)

    @staticmethod
    def _latest_file_in_workspace(workspace: Path) -> Optional[str]:
        polyglot_exts = {".py", ".go", ".rs", ".c", ".cpp", ".cc", ".cxx", ".js", ".mjs", ".ts", ".sh"}
        try:
            files = sorted(
                (p for p in Path(workspace).rglob("*") if p.is_file() and p.suffix.lower() in polyglot_exts),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not files:
                return None
            return str(files[0].relative_to(workspace))
        except Exception:
            return None

    @staticmethod
    def _infer_filename_hint(subtask_desc: str, goal: str) -> str:
        combined = f"{subtask_desc} {goal}".lower()
        if any(k in combined for k in ("golang", " in go ", " go program", " go script", " go function", ".go")):
            return "main.go"
        if any(k in combined for k in ("rust", " in rust", " rust program", " cargo", ".rs")):
            return "main.rs"
        if any(k in combined for k in ("c++", "cpp", "cxx", ".cpp")):
            return "main.cpp"
        if any(k in combined for k in (" in c ", " c program", " c script", "gcc", ".c")):
            return "main.c"
        if any(k in combined for k in ("javascript", "node.js", "nodejs", " in js", ".js")):
            return "main.js"
        return "main.py"

    def retry_router_classify(self, exec_outcome: dict[str, Any]) -> Failure:
        """Bridge from executor envelope -> Failure struct used by RetryRouter."""
        from backend.orchestrator.retry import classify as _classify
        return _classify(exec_outcome)
