"""M3 audit: detect hidden retries in correction logs.

Scans eval/reports/*.json and flags corrections where (tool, args) was
unchanged across the correction boundary â€” i.e., the "recovery" was just
a retry and not a genuine mutation of call/facts/plan/plan+scope/stop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def find_hidden_retries(reports_dir: Path) -> list[dict[str, Any]]:
    hidden: list[dict[str, Any]] = []
    for fp in sorted(reports_dir.glob("*.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        steps = data.get("steps", [])
        corrections = data.get("corrections", [])

        for c in corrections:
            step_before_ix = c.get("step_ix", 0) - 1
            step_before = next((s for s in steps if s["step_ix"] == step_before_ix), None)
            step_after = next(
                (s for s in steps if s["step_ix"] > c.get("step_ix", 0)), None
            )

            if step_before and step_after:
                before_tool = step_before.get("tool", "")
                before_args = step_before.get("args", {})
                after_tool = step_after.get("tool", "")
                after_args = step_after.get("args", {})

                if before_tool == after_tool and before_args == after_args:
                    hidden.append(
                        {
                            "run_id": data.get("run_id", "?"),
                            "step_ix": c.get("step_ix"),
                            "mode": c.get("mode"),
                            "strategy": c.get("strategy"),
                            "tool": before_tool,
                            "args": str(before_args)[:200],
                        }
                    )
    return hidden


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    results = []
    for variant in ("self_correcting", "baseline"):
        dir_path = base / "eval" / "reports" / variant
        if dir_path.exists():
            results.extend(find_hidden_retries(dir_path))

    if results:
        print(f"[FAIL] Found {len(results)} hidden retries (unchanged tool+args):")
        for r in results:
            print(
                f"  Run {r['run_id']} step {r['step_ix']} mode={r['mode']} "
                f"tool={r['tool']} args={r['args']}"
            )
        sys.exit(1)
    else:
        print("[PASS] No hidden retries detected â€” all corrections mutate distinct objects.")
        sys.exit(0)


if __name__ == "__main__":
    main()

