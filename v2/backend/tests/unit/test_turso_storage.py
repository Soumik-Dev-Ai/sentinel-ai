"""Unit tests for Turso (libSQL) Hrana v2 client and remote store/vector integration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.db import store, turso
from backend.memory.vector_store import VectorStore


def test_turso_url_normalization_and_encoding(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://sentinel-test.turso.io/")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok-123")
    assert turso.is_configured() is True
    assert turso._base_url() == "https://sentinel-test.turso.io"

    assert turso._encode_arg(None) == {"type": "null"}
    assert turso._encode_arg(True) == {"type": "integer", "value": "1"}
    assert turso._encode_arg(42) == {"type": "integer", "value": "42"}
    assert turso._encode_arg(3.5) == {"type": "float", "value": 3.5}
    assert turso._encode_arg("abc") == {"type": "text", "value": "abc"}


def test_turso_execute_decodes_hrana_rows(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "https://sentinel-test.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok-123")

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "results": [
            {
                "type": "ok",
                "response": {
                    "type": "execute",
                    "result": {
                        "cols": [
                            {"name": "id", "decltype": "TEXT"},
                            {"name": "tokens", "decltype": "INTEGER"},
                            {"name": "cost", "decltype": "REAL"},
                        ],
                        "rows": [
                            [
                                {"type": "text", "value": "r1"},
                                {"type": "integer", "value": "1500"},
                                {"type": "float", "value": 0.025},
                            ]
                        ],
                    },
                },
            }
        ]
    }
    with patch("backend.db.turso.httpx.post", return_value=fake_resp) as mock_post:
        rows = turso.execute("SELECT id, tokens, cost FROM runs WHERE id = ?", ["r1"])
        assert rows == [{"id": "r1", "tokens": 1500, "cost": 0.025}]
        assert mock_post.call_args.args[0] == "https://sentinel-test.turso.io/v2/pipeline"


def test_store_routes_to_turso_and_falls_back(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "local.db")
    monkeypatch.setattr(store, "_turso_ready", False)
    monkeypatch.setenv("TURSO_DATABASE_URL", "https://sentinel-test.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok-123")

    with patch("backend.db.turso.execute") as mock_exec:
        mock_exec.return_value = []
        store.insert_run("run-1", "test goal", True, steps=2, tokens=100, cost=0.01)
        assert mock_exec.call_count >= 2  # schema + insert

    # Simulate Turso outage -> seamless SQLite fallback
    with patch("backend.db.turso.execute", side_effect=RuntimeError("offline")):
        store.insert_run("run-2", "offline goal", True, steps=1)
        got = store.get_run("run-2")
        assert got is not None and got["goal"] == "offline goal"


def test_vector_store_turso_sync_and_offline_fallback(tmp_path: Path, monkeypatch):
    # Without persist_dir, stays pure in-memory even if Turso env is set
    monkeypatch.setenv("TURSO_DATABASE_URL", "https://sentinel-test.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok-123")
    mem_only = VectorStore(persist_dir=None)
    mem_only.add("solved", "sort array", "used quicksort")
    assert len(mem_only.query_closest("sort array")) == 1

    # With persist_dir, calls Turso schema/load/add/query
    with patch("backend.db.turso.execute") as mock_exec:
        mock_exec.side_effect = [
            [],  # CREATE TABLE
            [],  # initial SELECT load
            [],  # INSERT OR IGNORE
            [    # vector_distance_cos SELECT
                {
                    "id": "abc",
                    "kind": "solved",
                    "goal": "binary search",
                    "summary": "O(log n)",
                    "error_signature": None,
                    "strategy": None,
                    "success": 1,
                    "created_ts": 100.0,
                    "metadata": "{}",
                    "sim": 0.91,
                }
            ],
        ]
        vs = VectorStore(persist_dir=tmp_path)
        vs.add("solved", "binary search", "O(log n)")
        hits = vs.query_closest("binary search", k=1)
        assert len(hits) == 1
        assert hits[0][0].goal == "binary search"
        assert hits[0][1] == 0.91
