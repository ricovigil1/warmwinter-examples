"""
Gate an agent's PR auto-merge with Warm Winter.

Run this in CI after your checks. It asks the gate whether this PR is
trustworthy enough to merge unsupervised, given how confident your checks are.
The gate ADVISES — the workflow (see auto-merge-gate.yml) gates the actual merge
step on the verdict. The honest outcome comes later: did `main` stay green / was
the PR reverted? — reported by report_outcome.py so the `auto_merge` cell learns.

Env:
  WARMWINTER_API_KEY  your gate key (mint on the dashboard)
  CI_CONFIDENCE       your trusted signal in [0,1] — see note below
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ["WARMWINTER_API_KEY"])

# A confidence signal YOU trust, normalized to [0,1]. Good sources: fraction of
# required checks passing, a normalized coverage delta, an eval/grader score, or
# your own heuristic. Don't fake it high — the gate is calibrated against real
# outcomes, so an honest signal is what makes it useful.
confidence = float(os.environ.get("CI_CONFIDENCE", "0.0"))

d = ww.decide(
    domain="agent",
    decision_type="auto_merge",
    stated_confidence=confidence,
    stakes="high",            # merging unsupervised is high-stakes
    on_ungrounded="abstain",  # no grounding yet → don't auto-merge; ask a human
)

print(f"Warm Winter: verdict={d.verdict} cell={d.cell_state} "
      f"calibrated={d.calibrated_confidence} id={d.decision_id}")
for r in d.reasons:
    print(f"  · {r}")

# Hand the verdict + decision id to the workflow so it can gate the merge step
# and stash the id for outcome reporting after the PR lands.
gh_out = os.environ.get("GITHUB_OUTPUT")
if gh_out:
    with open(gh_out, "a") as out:
        out.write(f"verdict={d.verdict}\n")
        out.write(f"decision_id={d.decision_id}\n")
