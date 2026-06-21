"""
Gate a support reply with Warm Winter — auto-resolve the ticket, or route it to a
human? The two failure modes of support automation are a confidently-wrong auto-reply
and over-escalating everything; the gate is calibrated triage between them.

The verifier is what happens next: the ticket reopening (or a bad CSAT) is a failure;
no reopen is a success. `guard()` gates, sends or routes, and auto-reports.

    pip install warmwinter
"""
import os
from warmwinter import WarmWinter

ww = WarmWinter(api_key=os.environ.get("WARMWINTER_API_KEY", "ww_..."))


def handle_ticket(ticket, draft, *, confidence, send_reply, route_to_human, reopened):
    """Auto-reply if the gate trusts it; otherwise route to a human. The reopen
    check closes the loop so the `support_reply` cell learns which ticket types it
    can actually own."""
    return ww.guard(
        domain="support",
        decision_type="support_reply",
        stated_confidence=confidence,
        cheap=lambda: send_reply(ticket, draft),    # auto-resolve
        escalate=lambda: route_to_human(ticket),    # safe fallback
        verify=lambda _: not reopened(ticket),       # success = it didn't bounce back
    )


if __name__ == "__main__":
    out = handle_ticket(
        ticket={"id": 42}, draft="Here's how to reset your password…",
        confidence=0.74,
        send_reply=lambda t, d: print("  auto-replied to", t["id"]),
        route_to_human=lambda t: print("  routed", t["id"], "to a human"),
        reopened=lambda t: False,
    )
