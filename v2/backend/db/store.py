"""Persistent storage for Sentinel AI run history (Turso remote + SQLite fallback)."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from backend.db import turso

_DB_PATH = Path.home() / ".sentinel_ai" / "history.db"
_RUNS_SCHEMA = """
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
"""
_turso_ready = False


def _ensure_turso() -> bool:
    global _turso_ready
    if not turso.is_configured():
        return False
    if not _turso_ready:
        turso.execute(_RUNS_SCHEMA)
        _turso_ready = True
    return True


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(_RUNS_SCHEMA)
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
    params = [
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
    ]
    try:
        if _ensure_turso():
            turso.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                params,
            )
            return
    except Exception:
        pass

    conn = _get_conn()
    conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)", params)
    conn.commit()
    conn.close()


def list_runs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    try:
        if _ensure_turso():
            return turso.execute(
                "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                [limit, offset],
            )
    except Exception:
        pass

    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    try:
        if _ensure_turso():
            rows = turso.execute("SELECT * FROM runs WHERE id = ?", [run_id])
            return rows[0] if rows else None
    except Exception:
        pass

    conn = _get_conn()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
