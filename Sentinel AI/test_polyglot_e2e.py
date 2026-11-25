from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.orchestrator.pipeline import MultiAgentPipeline

def main():
    print("=== Sentinel AI 2.0: Starting Polyglot Pipeline E2E Test ===")
    p = MultiAgentPipeline()
    ws = Path(tempfile.mkdtemp(prefix="e2e_polyglot_"))
    print(f"Temporary workspace created at: {ws}")

    res = p.run(
        goal="Write a Python script that calculates factorial of numbers up to 10 and asserts correctness",
        acceptance=["Must assert factorial(5) == 120", "Must print ALL TESTS PASSED"],
        workspace=ws,
    )
    print("\n" + "=" * 50)
    print(f"RUN SUCCESS: {res.get('success')}")
    print("=" * 50)
    print(res.get("final_output", ""))

if __name__ == "__main__":
    main()
