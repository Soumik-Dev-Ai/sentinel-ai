"""Minimal Turso (libSQL) Hrana HTTP v2 client over httpx."""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx


def _base_url() -> str:
    url = os.getenv("TURSO_DATABASE_URL", "").strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return url


def _auth_token() -> str:
    return os.getenv("TURSO_AUTH_TOKEN", "").strip()


def is_configured() -> bool:
    return bool(_base_url() and _auth_token())


def _encode_arg(val: Any) -> dict[str, Any]:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    return {"type": "text", "value": str(val)}


def _decode_cell(cell: dict[str, Any]) -> Any:
    t = cell.get("type")
    if t == "null":
        return None
    val = cell.get("value")
    if t == "integer":
        return int(val) if val is not None else None
    if t == "float":
        return float(val) if val is not None else None
    return val


def execute_many(
    stmts: list[tuple[str, Optional[list[Any]]]],
    timeout: float = 10.0,
) -> list[list[dict[str, Any]]]:
    """Execute SQL statements in one Hrana v2 HTTP pipeline call."""
    url = f"{_base_url()}/v2/pipeline"
    token = _auth_token()
    requests_payload: list[dict[str, Any]] = [
        {
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [_encode_arg(a) for a in (args or [])],
            },
        }
        for sql, args in stmts
    ]
    requests_payload.append({"type": "close"})

    resp = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"baton": None, "requests": requests_payload},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    outputs: list[list[dict[str, Any]]] = []
    for item in data.get("results", [])[: len(stmts)]:
        if item.get("type") == "error":
            msg = item.get("error", {}).get("message", "Turso SQL error")
            raise RuntimeError(msg)
        result = item.get("response", {}).get("result", {})
        cols = [c["name"] for c in result.get("cols", [])]
        rows = [
            {col: _decode_cell(cell) for col, cell in zip(cols, row)}
            for row in result.get("rows", [])
        ]
        outputs.append(rows)
    return outputs


def execute(
    sql: str,
    args: Optional[list[Any]] = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Execute a single SQL statement against Turso and return row dicts."""
    return execute_many([(sql, args)], timeout=timeout)[0]
