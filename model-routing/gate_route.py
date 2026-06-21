"""
Gate model routing with Warm Winter — is the cheap model trustworthy enough for
this call, or should you escalate to the expensive one?

This is the cost recipe: on the verified compute cell, the cheap model keeps ~95%
of the quality at 57% of the cost. The gate decides per call; you report whether
the answer held, and the cell sharpens.

    pip install warmwinter
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ.get("WARMWINTER_API_KEY", "ww_..."))


def answer(prompt, *, confidence, cheap_model, big_model, grade):
    """Route the prompt: cheap if the gate trusts it here, else escalate. `grade`
    is your success test (an eval, a thumbs-up, a downstream check)."""
    d = ww.decide(
        domain="compute",
        decision_type="model_route",
        stated_confidence=confidence,   # how sure you are the cheap model suffices
        stakes="medium",
    )
    out = cheap_model(prompt) if d.verdict == "act" else big_model(prompt)
    ww.outcome(d.decision_id, "success" if grade(out) else "failure")
    return out


# Or the whole loop in one call — gate, run the chosen model, auto-report:
def answer_guarded(prompt, *, confidence, cheap_model, big_model, grade):
    return ww.guard(
        domain="compute", decision_type="model_route", stated_confidence=confidence,
        cheap=lambda: cheap_model(prompt),
        escalate=lambda: big_model(prompt),
        verify=lambda out: grade(out),
    )


if __name__ == "__main__":
    cheap = lambda p: f"[cheap] {p[:40]}"
    big = lambda p: f"[big] {p[:40]}"
    print(answer("summarize this ticket", confidence=0.82,
                 cheap_model=cheap, big_model=big, grade=lambda o: o is not None))
