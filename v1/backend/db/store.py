"""SQLite persistent storage for Sentinel AI run history."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


_DB_PATH = Path.home() / ".sentinel_ai" / "history.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            goal TEXT NOT NULL,
            success INTEGER NOT NULL,
            steps INTEGER NOT NULL DEFAULT 0,
            corrections INTEGER NOT NULL DEFAULT 0,
            elapsed REAL NOT NULL DEFAULT 0,
            provider TEXT NOT NULL DEFAULT '',
            tokens INTEGER NOT NULL DEFAULT 0,
            cost REAL NOT NULL DEFAULT 0,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.commit()
    return conn


def insert_run(
    run_id: str,
    goal: str,
    success: bool,
    steps: int = 0,
    corrections: int = 0,
    elapsed: float = 0.0,
    provider: str = "",
    tokens: int = 0,
    cost: float = 0.0,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            int(time.time()),
            goal,
            int(success),
            steps,
            corrections,
            elapsed,
            provider,
            tokens,
            cost,
            json.dumps(metadata or {}),
        ),
    )
    conn.commit()
    conn.close()


def list_runs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
