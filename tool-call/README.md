# Tool-call gate

Should an agent execute this tool call, or stop and ask a human? Stakes scale with
**reversibility** — a read is cheap to be wrong about; an irreversible write
(refund, delete, send, post) is not, so the gate abstains rather than guess.

## Files

- **`gate_tool.py`** — framework-agnostic `guarded_call(...)` wrapper: gate →
  execute the chosen path → report the outcome. Runs as a toy demo out of the box.
- **`langgraph_tool.py`** — a `gated(tool)` helper for LangGraph / LangChain that
  wraps any tool so the agent can't fire a high-stakes action ungrounded.

## The pattern

```python
d = ww.decide(domain="agent", decision_type=f"tool:{name}",
              stated_confidence=conf,
              stakes="high" if irreversible else "medium",
              on_ungrounded="abstain")
if d.verdict == "act":
    result = run(name, args)
    ww.outcome(d.decision_id, "success" if ok(result) else "failure")
else:
    escalate_to_human(name, args)   # never execute on a guess
```

The gate never runs the tool for you — it tells you whether *you* should. The
outcome you report is what turns `tool:issue_refund` from a seeded guess into a
calibrated call over time.
