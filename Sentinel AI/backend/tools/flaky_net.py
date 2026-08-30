from __future__ import annotations

import hashlib
import random
from typing import Any

from pydantic import BaseModel

from backend.tools.base import ToolFailureError, ToolProtocol


class InstallPackageArgs(BaseModel):
    package: str


class InstallPackageResult(BaseModel):
    package: str
    installed: bool
    version: str


_CACHE = {
    "hashhelper": "1.0.0",
    "python-utils": "0.9.5",
    "stdhash": "0.8.1",
}


class FlakyNetTool(ToolProtocol):
    name = "flaky_net"
    description = "Install a package (intermittently fails / returns malformed schema)."
    args_schema = InstallPackageArgs
    return_schema = InstallPackageResult

    def __init__(self, seed: int | None = 42):
        self._rng = random.Random(seed)

    def _invoke(self, args: InstallPackageArgs) -> dict[str, Any]:  # type: ignore[override]
        pkg = args.package.strip().lower()
        if pkg in (c.lower() for c in _CACHE):
            version = _CACHE[[c for c in _CACHE if c.lower() == pkg][0]]
            return {"package": pkg, "installed": True, "version": version}

        if self._rng.random() < 0.4:
            raise ToolFailureError("Network timeout", "flaky_net", {"pkg": pkg})

        if self._rng.random() < 0.3:
            return {"package": pkg, "installed": True}

        version = hashlib.sha256(pkg.encode()).hexdigest()[:8]
        return {"package": pkg, "installed": True, "version": version}

