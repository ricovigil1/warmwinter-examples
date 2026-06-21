# Model-routing gate

Is the cheap model trustworthy enough for this call, or should you escalate to the
expensive one? This is the cost recipe — on the verified compute cell, the cheap
model keeps **~95% of the quality at 57% of the cost**.

- **`gate_route.py`** — `decide(domain="compute", decision_type="model_route", …)`,
  run the chosen model, report whether the answer held. Includes a one-call
  `guard()` variant. Runs as a toy demo out of the box.

```python
d = ww.decide(domain="compute", decision_type="model_route",
              stated_confidence=0.82, stakes="medium")
answer = cheap_model(prompt) if d.verdict == "act" else big_model(prompt)
ww.outcome(d.decision_id, "success" if ok else "failure")
```

Routing is the commodity; knowing *when* the cheap model is actually safe to trust
is the part the gate calibrates. Feed it an honest confidence signal — it's scored
against what actually happens.
