"""
Gate an agent's tool call with Warm Winter.

Before an agent executes a tool — especially an irreversible one (sending money,
deleting data, posting publicly) — ask whether it's trustworthy enough to run, or
whether to stop and hand off to a human. Stakes scale with reversibility: a
reversible read is low-stakes; an irreversible write is high-stakes and the gate
abstains rather than guess.

    pip install warmwinter
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ.get("WARMWINTER_API_KEY", "ww_..."))


def guarded_call(name, args, *, agent_confidence, irreversible=False,
                 execute=None, escalate=None):
    """Run `execute(name, args)` only if the gate trusts it; else `escalate(...)`.
    Reports the outcome so the per-tool cell learns."""
    d = ww.decide(
        domain="agent",
        decision_type=f"tool:{name}",
        stated_confidence=agent_confidence,
        stakes="high" if irreversible else "medium",
        on_ungrounded="abstain",   # never execute an irreversible guess
    )

    if d.verdict == "act":
        result = execute(name, args)
        ok = result is not None            # replace with your real success test
        ww.outcome(d.decision_id, "success" if ok else "failure")
        return result

    # escalate / abstain → don't execute; route to a human (or a safer path)
    return escalate(name, args) if escalate else None


if __name__ == "__main__":
    # Toy demo: a reversible read sails through; an irreversible write on a thin
    # cell is held back until the gate has earned the right to clear it.
    def execute(name, args): print(f"  executed {name}({args})"); return {"ok": True}
    def escalate(name, args): print(f"  escalated {name}({args}) to a human"); return None

    guarded_call("search_docs", {"q": "refund policy"}, agent_confidence=0.88,
                 irreversible=False, execute=execute, escalate=escalate)
    guarded_call("issue_refund", {"amount": 500}, agent_confidence=0.62,
                 irreversible=True, execute=execute, escalate=escalate)
