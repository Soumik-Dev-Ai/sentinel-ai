from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.ai_agent.working_memory import WorkingMemory


class RunLogger:
    def __init__(self, output_dir: Path | None = None):
        from backend import config

        self._output_dir = output_dir or config.EVAL_REPORTS_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def persist(self, memory: WorkingMemory) -> Path:
        data = memory.to_dict()
        path = (
            self._output_dir / f"{memory.goal.id}_{memory.run_id}.json"
            if memory.goal
            else self._output_dir / f"{memory.run_id}.json"
        )
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def load(self, path: Path) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    @staticmethod
    def serialize(memory: WorkingMemory) -> str:
        return json.dumps(memory.to_dict(), indent=2, default=str)

    @staticmethod
    def deserialize(data: str) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(data)
        return result


