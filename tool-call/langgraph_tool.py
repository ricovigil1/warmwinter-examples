"""
Drop Warm Winter into a LangGraph / LangChain agent as a guard around tool calls.

The gate decides whether the agent's chosen tool is trustworthy enough to run; an
ungrounded high-stakes call is held for a human instead of executed on a guess.
This wraps any LangChain tool without changing the tool itself.

    pip install warmwinter langchain-core
"""
import os
from warmwinter import WarmWinter
from langchain_core.tools import tool, BaseTool

ww = WarmWinter(api_key=os.environ.get("WARMWINTER_API_KEY", "ww_..."))


def gated(t: BaseTool, *, irreversible: bool = False, confidence: float = 0.7) -> BaseTool:
    """Return a tool that asks Warm Winter before it runs the wrapped tool `t`."""
    @tool(t.name, description=t.description)
    def _wrapped(**kwargs):
        d = ww.decide(
            domain="agent", decision_type=f"tool:{t.name}",
            stated_confidence=confidence,
            stakes="high" if irreversible else "medium",
            on_ungrounded="abstain",
        )
        if d.verdict != "act":
            return (f"[held by Warm Winter: {d.verdict} — this action wasn't "
                    f"grounded enough to run unsupervised; ask a human]")
        result = t.invoke(kwargs)
        ww.outcome(d.decision_id, "success")   # close the loop with your real test
        return result
    return _wrapped


# Example: wrap a sensitive tool so the agent can't fire it on a hunch.
@tool
def delete_account(user_id: str) -> str:
    """Permanently delete a user account."""
    return f"deleted {user_id}"


safe_delete = gated(delete_account, irreversible=True)
# ... add `safe_delete` to your agent's tools instead of the raw `delete_account`.
