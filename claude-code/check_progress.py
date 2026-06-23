#!/usr/bin/env python3
"""Check your dogfood progress: how the agent_ops cells are calibrating.

    WARMWINTER_API_KEY=ww_... python check_progress.py

Prints every cell the gate is tracking for your key, newest signal first, with the
one number that matters per cell: n (resolved outcomes) and its state. Cells need
n>=30 + good calibration to reach `verified` (when the gate will `act` on its own).
No LLM, effectively free — it's a read.
"""
import os
import sys

from warmwinter import WarmWinter, WarmWinterError

KEY = os.environ.get("WARMWINTER_API_KEY")
if not KEY:
    sys.exit("Set WARMWINTER_API_KEY first (the key you minted at /api/v1/gate/keys).")

ww = WarmWinter(api_key=KEY, base_url=os.environ.get("WARMWINTER_BASE_URL", "https://api.warmwinter.io"))

try:
    cells = ww.frontier().get("cells", [])
except WarmWinterError as e:
    sys.exit(f"Couldn't reach the gate: {e}")

# Your dogfood cells (live, from your own coding) vs the shared backtest seed cells.
live = [c for c in cells if c.get("source") == "live"]
seed = [c for c in cells if c.get("source") != "live"]

def row(c):
    dt = c.get("prediction_type", "?")
    n = c.get("n", 0)
    state = c.get("state", "?")
    rel = c.get("reliability")
    rel = f"{rel:.3f}" if isinstance(rel, (int, float)) else "—"
    # how far to verified: needs n>=30
    bar = min(int(n), 30)
    prog = "#" * (bar // 2) + "." * ((30 - bar) // 2)
    return f"  {dt:<16} n={n:<4} {state:<11} reliability={rel:<7} [{prog}] {min(n,30)}/30"

print("\n=== YOUR live cells (from your own coding — this is the dogfood signal) ===")
if live:
    for c in sorted(live, key=lambda c: -c.get("n", 0)):
        print(row(c))
else:
    print("  (none yet — code in this repo with the hook active, then re-run)")

verified_live = sum(1 for c in live if c.get("state") == "verified")
print(f"\n  {len(live)} live cell(s); {verified_live} verified. "
      f"Flip WW_GATE_MODE=enforce once the ones you care about reach 'verified'.")

print("\n=== shared backtest SEED cells (every account starts with these) ===")
for c in sorted(seed, key=lambda c: c.get("prediction_type", "")):
    dt = c.get("prediction_type", "?")
    state = c.get("state", "?")
    note = c.get("metric") or c.get("regime") or ""
    print(f"  {dt:<16} {state:<11} {note}")
