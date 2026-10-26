"""Unreleased source SDK required. Executes only local Python; records metadata.

Run only with the owner's permission to create a canonical run and Gate decision.
Provision a runtime-bound Gate credential privately in WARMWINTER_API_KEY.
"""
import os
import uuid
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ["WARMWINTER_API_KEY"])
ref = str(uuid.uuid4())
run = ww.run(objective_ref="review-local-result", authority_ref="observation-only",
             external_run_ref=ref)
result = ww.guard(domain="example", decision_type="review", stated_confidence=0.6,
                  run_id=run["id"], cheap=lambda: 2 + 2, escalate=lambda: 2 + 2)
ww.run_event(run["id"], "action", idempotency_key=ref + ":action",
             execution_status="succeeded", receipt_ref="local:arithmetic")
ww.run_event(run["id"], "verification", idempotency_key=ref + ":verification",
             verification_status="passed" if result == 4 else "failed",
             verification_ref="local:self-check")
ww.run_event(run["id"], "outcome", idempotency_key=ref + ":outcome", outcome=float(result == 4))
ww.run_event(run["id"], "usefulness", idempotency_key=ref + ":usefulness", usefulness="useful")
ww.run_event(run["id"], "complete", idempotency_key=ref + ":complete", execution_status="succeeded")
# Self-checks and outcomes above are weak evidence, never independent verification.
print("Canonical run:", run["id"])
