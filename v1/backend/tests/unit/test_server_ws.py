"""Tests for the API server WebSocket error paths using TestClient."""
from __future__ import annotations

import pytest


@pytest.mark.skipif(True, reason="Requires starlette.testclient + agent runtime")
def test_ws_timeout() -> None:
    pass

