"""Unit tests for the intentionally flaky tool."""

from __future__ import annotations

from backend.tools.flaky_net import FlakyNetTool


def test_cached_package_succeeds_deterministically() -> None:
    tool = FlakyNetTool(seed=42)
    out = tool.invoke({"package": "hashhelper"})
    assert out["ok"] is True
    assert out["result"]["installed"] is True
    assert "version" in out["result"]


def test_seeded_flakiness_has_some_failures() -> None:
    tool = FlakyNetTool(seed=99)
    failures = 0
    for _ in range(50):
        out = tool.invoke({"package": "nonexistent-pkg"})
        if not out["ok"]:
            failures += 1
    assert failures > 0


def test_tool_name_is_flaky_net() -> None:
    assert FlakyNetTool().name == "flaky_net"

