"""
Close the loop on an auto-merge decision.

The point of the gate is that it learns from *real* outcomes — so after a gated
PR lands, tell Warm Winter whether the bet held. Run this from the workflow that
watches `main` (or on a short delay): if main stayed green and the PR wasn't
reverted, the merge was a success; otherwise it's a failure. That single signal
is what moves the `auto_merge` cell from a seeded guess to a verified call.

Env:
  WARMWINTER_API_KEY   your gate key
  WW_DECISION_ID       the decision_id emitted by gate_merge.py for this PR
  WW_OUTCOME           "success" or "failure"
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ["WARMWINTER_API_KEY"])

decision_id = os.environ["WW_DECISION_ID"]
outcome = os.environ.get("WW_OUTCOME", "success")

res = ww.outcome(
    decision_id, outcome,
    observed={"signal": "main_ci_after_merge", "label_strength": "strong"},
)
print(f"Warm Winter: reported {outcome} for {decision_id} → {res}")
