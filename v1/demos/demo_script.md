# Demo Script — Self-Correcting Multi-Step Agent

This script walks through 3 visible self-corrections using goal G5 (flaky_net),
G2 (goal drift), and G4 (insufficient information). Run with the self-correcting
variant; the baseline variant will fail or loop on the same goals.

---

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env
# Add at least ANTHROPIC_API_KEY
python -m eval.run_eval --goals G5 G2 G4
```

---

## Scene 1: F1 ToolFailure (flaky_net malformed schema)

**Goal G5** — Install a package via `flaky_net.install_package`.

```
Step 3: flaky_net.install_package("hashhelper")
  → BUG: returns {"package":"hashhelper","installed":true}
    (missing "version" → shape_violation)
```

**Self-correction detected:**
1. `SelfEvaluator` classifies mode=F1
2. `RecoveryController` decrements budget (3→2)
3. `strategy_tool_failure` re-invokes with sanitized args
4. Tool succeeds on retry with conforming schema
5. Agent advances to next subtask

**Expected output in terminal viewer:**
```
┌─────────────────────────────────────────┐
│ Step 3 │ CORRECTION F1 │ tool_failure  │
│ Object: call  │ Budget: 2              │
└─────────────────────────────────────────┘
```

---

## Scene 2: F3 GoalDrift (recursive → iterative)

**Goal G2** — "Implement fib ITERATIVELY in O(1) memory."

```
Step 2: LLM writes recursive fib → tests pass
```

**Self-correction:**
1. `SelfEvaluator` detects: success=True, plan_valid=False
   — "acceptance: O(1) memory; current impl is O(n) stack"
2. `RecoveryController` decrements budget (3→2)
3. `strategy_goal_drift` discards remaining subtask plan
4. Generates new subtasks: [impl iterative O(1), re-run with complexity gate]
5. Next iteration writes correct iterative implementation

**Expected output:**
```
┌─────────────────────────────────────────┐
│ Step 4 │ CORRECTION F3 │ goal_drift    │
│ Object: plan │ New plan: ["impl...",   │
│   "re-run tests"] │ Budget: 2          │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ Step 5 │ OK │ Plan: 2/3 complete       │
└─────────────────────────────────────────┘
```

---

## Scene 3: F4 InsufficientInformation (read-before-edit)

**Goal G4** — "Fix an off-by-one in `mod.py`. Read it first."

```
Step 1: LLM tries to edit mod.py without reading
```

**Self-correction:**
1. `SelfEvaluator` detects: world_model has no content hash for `mod.py`
   — mode=F4, evidence="required input missing"
2. `strategy_insufficient_information` inserts gather-subtask before current
3. Budget decremented (3→2)
4. Next step reads `mod.py` → populates world_model
5. Edit proceeds with full context → fix applied correctly

**Expected output:**
```
┌─────────────────────────────────────────┐
│ Step 2 │ CORRECTION F4 │ insufficient  │
│ Object: plan+scope │ Inserted: read    │
│   mod.py │ Budget: 2                   │
└─────────────────────────────────────────┘
```

---

## Verification

After all 3 scenes, inspect:

```bash
# CLI viewer
python -m src.io.viewer_cli eval/reports/G5_*.json --show-corrections
python -m src.io.viewer_cli eval/reports/G2_*.json --show-corrections
python -m src.io.viewer_cli eval/reports/G4_*.json --show-corrections

# HTML viewer
python -m src.io.viewer_html eval/reports/G5_*.json --open
```

Each run log should contain:
- `corrections[]` with the relevant F1/F3/F4 entries
- `provider_events[]` (any fallback chain switches)
- `final_output` with the completed artifact

---

## Baseline Contrast

Run the same goals without self-correction:

```bash
python -m eval.run_eval --goals G5 G2 G4 --baseline-only
```

Expected: G5 loops on flaky failures, G2 writes recursive fib and reports
"done" (violating the iterative requirement), G4 edits before reading and
introduces a new bug.
