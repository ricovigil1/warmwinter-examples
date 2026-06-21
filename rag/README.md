# RAG grounding gate

Is the retrieval grounded enough to answer, or should the model **abstain** instead
of guessing? Targets the classic RAG failure: a confident answer built on thin or
irrelevant context.

- **`gate_rag.py`** — `decide(domain="rag", decision_type="rag_answer",
  on_ungrounded="abstain")`. On an ungrounded cell it returns abstain, and you
  answer "I don't know" rather than hallucinate. Runs as a toy demo.

```python
d = ww.decide(domain="rag", decision_type="rag_answer",
              stated_confidence=retrieval_score(hits), on_ungrounded="abstain")
answer = generate(q, hits) if d.verdict == "act" else "I don't know that yet."
ww.outcome(d.decision_id, "success" if not user_corrected else "failure")
```

The outcome signal is a correction / thumbs-down / eval. Honest "I don't know"
beats confident-wrong — and the cell learns which questions your retrieval can
actually ground.
