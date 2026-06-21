# Support-reply gate

Auto-resolve the ticket, or route it to a human? Support automation has two failure
modes — a confidently-wrong auto-reply, and over-escalating everything to a human.
The gate is calibrated triage between them.

- **`gate_support.py`** — one `guard()` call: gate, send the reply or route to a
  human, and auto-report. Runs as a toy demo.

```python
reply = ww.guard(
    domain="support", decision_type="support_reply", stated_confidence=confidence,
    cheap=lambda: send_reply(ticket, draft),   # auto-resolve
    escalate=lambda: route_to_human(ticket),   # safe fallback
    verify=lambda _: not reopened(ticket),     # reopen = failure; auto-reports
)
```

The verifier is what happens next — a reopened ticket (or a bad CSAT) is a failure.
The `support_reply` cell learns which ticket types it can actually own.
