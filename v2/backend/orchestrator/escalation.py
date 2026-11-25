"""Confidence-based escalation manager — human-in-the-loop.

If a subtask has accumulated N=2 self-corrections AND the system's internal
confidence drops below THRESHOLD=0.50, the manager pauses execution, emits a
`needs_human_review` event over the WebSocket, and waits for a
`resume_from_human` Web-RTC-style message before continuing.

The orchestrator pipeline calls `await maybe_escalate(subtask, ...)` after
each retry; the call blocks (in the agent's worker thread) until the user
responds or a timeout fires.

Because we run inside a worker thread (not asyncio), the wait uses a
`threading.Event` with a finite timeout, and the FastAPI server's WebSocket
handler is the one that -- upon receiving a message from the user -- calls
`EscalationManager.answer(id, text)` to release the wait.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.orchestrator.base import AgentContext


ESCALATION_THRESHOLD = 0.50      # confidence < 0.5
ESCALATION_MAX_ATTEMPTS = 4     # >=4 self-corrections on same subtask (do not interrupt early)
ESCALATION_TIMEOUT_SECONDS = 300  # if the user doesn't answer in 5 minutes, give up


@dataclass
class PendingEscalation:
    """A suspended escalation waiting for human input."""
    id: str
    subtask_id: str
    question: str
    context_summary: dict[str, Any]
    wait_event: threading.Event = field(default_factory=threading.Event)
    answer: Optional[str] = None
    deadline_ts: float = 0.0

    def is_pending(self) -> bool:
        return not self.wait_event.is_set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subtask_id": self.subtask_id,
            "question": self.question,
            "context_summary": self.context_summary,
            "timeout_seconds": max(0.0, self.deadline_ts - time.time()),
        }


class EscalationManager:
    """Tracks per-subtask correction counts and brokers human-in-the-loop pauses."""

    def __init__(
        self,
        threshold: float = ESCALATION_THRESHOLD,
        max_attempts: int = ESCALATION_MAX_ATTEMPTS,
        timeout_seconds: float = ESCALATION_TIMEOUT_SECONDS,
    ) -> None:
        self._threshold = threshold
        self._max_attempts = max_attempts
        self._timeout_seconds = timeout_seconds
        self._lock = threading.RLock()
        self._attempts: dict[str, int] = {}
        self._confidences: dict[str, list[float]] = {}
        self._pending: dict[str, PendingEscalation] = {}  # escalation_id -> Pending
        self._subtask_pending: dict[str, str] = {}  # subtask_id -> escalation_id

    # ---------- counts + confidence ----------

    def record_attempt(
        self,
        subtask_id: str,
        confidence: float,
    ) -> None:
        with self._lock:
            self._attempts[subtask_id] = self._attempts.get(subtask_id, 0) + 1
            self._confidences.setdefault(subtask_id, []).append(float(confidence))

    def reset(self, subtask_id: str) -> None:
        with self._lock:
            self._attempts.pop(subtask_id, None)
            self._confidences.pop(subtask_id, None)
            eid = self._subtask_pending.pop(subtask_id, None)
            if eid:
                self._pending.pop(eid, None)

    def average_confidence(self, subtask_id: str) -> float:
        c = self._confidences.get(subtask_id) or []
        return sum(c) / len(c) if c else 1.0

    def attempts(self, subtask_id: str) -> int:
        return self._attempts.get(subtask_id, 0)

    # ---------- gating ----------

    def should_escalate(self, subtask_id: str) -> bool:
        attempts = self.attempts(subtask_id)
        conf = self.average_confidence(subtask_id)
        return attempts >= self._max_attempts and conf < self._threshold

    # ---------- request + answer ----------

    def request(
        self,
        ctx: AgentContext,
        subtask_id: str,
        question: str,
        context_summary: Optional[dict[str, Any]] = None,
    ) -> PendingEscalation:
        """Emit `needs_human_review` and block (in caller's thread) until answer or timeout."""
        escalation_id = uuid.uuid4().hex[:12]
        essc = PendingEscalation(
            id=escalation_id,
            subtask_id=subtask_id,
            question=question,
            context_summary=context_summary or {},
            deadline_ts=time.time() + self._timeout_seconds,
        )
        with self._lock:
            self._pending[escalation_id] = essc
            self._subtask_pending[subtask_id] = escalation_id

        ctx.bus.emit(
            "needs_human_review",
            escalation_id=escalation_id,
            subtask_id=subtask_id,
            question=question,
            confidence=self.average_confidence(subtask_id),
            context_summary=context_summary or {},
            timeout_seconds=self._timeout_seconds,
        )
        ctx.bus.emit(
            "terminal_line",
            text=(
                f"[ESCALATE] {question}\n"
                f"            attempts={self._attempts.get(subtask_id)} "
                f"conf={self.average_confidence(subtask_id):.2f} "
                f"timeout={self._timeout_seconds}s — waiting for human..."
            ),
            line_type="recovery",
        )
        return essc

    def wait_until_answer(self, escalation: PendingEscalation) -> Optional[str]:
        """Block the calling worker thread until human answers OR timeout.

        Returns the answer text on success or None on timeout.
        """
        remaining = escalation.deadline_ts - time.time()
        if remaining <= 0:
            return None
        # Wait in 1s slices so timeouts remain responsive even if the answer
        # never arrives (Python's Event.wait returns True if set, False on timeout).
        while remaining > 0:
            if escalation.wait_event.wait(min(1.0, remaining)):
                return escalation.answer
            # If pending dropped off externally, abort.
            if escalation.id not in self._pending:
                return None
            remaining = escalation.deadline_ts - time.time()
        return None

    def answer(self, escalation_id: str, answer_text: str) -> bool:
        """Called by the WebSocket thread when the user replies.

        Returns False if the escalation doesn't exist or was already answered.
        """
        with self._lock:
            esc = self._pending.get(escalation_id)
            if esc is None or esc.wait_event.is_set():
                return False
            esc.answer = answer_text
            esc.wait_event.set()
            self._subtask_pending.pop(esc.subtask_id, None)
        return True

    def cancel(self, escalation_id: str) -> None:
        with self._lock:
            esc = self._pending.pop(escalation_id, None)
            if esc is not None:
                esc.wait_event.set()
                self._subtask_pending.pop(esc.subtask_id, None)

    def has_pending_for(self, subtask_id: str) -> bool:
        return subtask_id in self._subtask_pending

    def pending(self) -> list[PendingEscalation]:
        with self._lock:
            return list(self._pending.values())


# Module-level singleton used by the WebSocket handler as a default.
# Per-run instances should be provided by the pipeline and wired to the
# server directly (see pipeline.py -> _active_escalation).
GLOBAL_ESCALATION_MANAGER = EscalationManager()
