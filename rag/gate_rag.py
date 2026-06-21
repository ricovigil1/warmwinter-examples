"""
Gate a RAG answer with Warm Winter — is the retrieval grounded enough to answer,
or should the model abstain instead of guessing off the frontier?

The failure mode this targets: a confident answer built on thin or irrelevant
context. Pass your retrieval confidence in; on an ungrounded cell at answer-stakes
the gate says abstain, and you return "I don't know" rather than hallucinate.

    pip install warmwinter
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ.get("WARMWINTER_API_KEY", "ww_..."))


def answer_with_rag(question, *, retrieve, retrieval_score, generate, was_corrected):
    hits = retrieve(question)

    d = ww.decide(
        domain="rag",
        decision_type="rag_answer",
        stated_confidence=retrieval_score(hits),   # your confidence the context supports an answer
        on_ungrounded="abstain",                    # don't guess off the frontier
    )

    if d.verdict != "act":
        return "I don't know that yet."             # abstain — honest beats confident-wrong

    ans = generate(question, hits)
    # Close the loop when you learn the truth: a correction / thumbs-down / eval.
    ww.outcome(d.decision_id, "failure" if was_corrected(ans) else "success")
    return ans


if __name__ == "__main__":
    print(answer_with_rag(
        "what's our refund window?",
        retrieve=lambda q: ["context about refunds"],
        retrieval_score=lambda hits: 0.83,
        generate=lambda q, hits: "30 days.",
        was_corrected=lambda ans: False,
    ))
