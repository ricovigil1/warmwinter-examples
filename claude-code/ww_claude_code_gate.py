#!/usr/bin/env python3
"""Gate a Claude Code agent's tool calls through Warm Winter.

Wire this as BOTH a PreToolUse and a PostToolUse hook (see settings.snippet.json).

  pre  : before a tool runs, ask the gate act | escalate | abstain
         → maps to Claude Code's allow | ask | ask, and the agent proceeds,
           asks you, or backs off accordingly.
  post : after the tool runs, report the outcome so the cell calibrates and
         earns (or loses) autonomy over time.

Cost note: /gate/decide has no LLM in it — it's a calibrated-cell lookup, so this
is effectively free against your own deployment. `escalate` means "ask the human",
not "spend more compute".

Modes (WW_GATE_MODE):
  shadow  — OBSERVE ONLY (recommended for the first ~2 weeks). Records every decision
            and outcome so cells calibrate, but emits NO permission decision: Claude
            Code's normal allow/ask flow runs untouched. Zero friction, same live
            cells. Use this to warm cold cells before you let the gate steer.
  enforce — the gate's verdict drives Claude Code: act→allow, escalate/abstain→ask.
            Flip to this once cells you care about have verified.
  (default: shadow — safe.)

Env:  WARMWINTER_API_KEY   (mint at /api/v1/gate/keys)
      WARMWINTER_BASE_URL  (optional; defaults to the hosted API, api.warmwinter.io)
      WW_GATE_MODE         (shadow | enforce; default shadow)
"""
import sys
import os
import json
import hashlib
import tempfile

# the published SDK: `pip install warmwinter`
from warmwinter import WarmWinter, WarmWinterError

STATE = os.path.join(tempfile.gettempdir(), "ww_gate_decisions.json")
DOMAIN = "agent_ops"
MODE = os.environ.get("WW_GATE_MODE", "shadow").lower()   # shadow (observe) | enforce


# ── classify a tool call into (decision_type, stakes, confidence) ────────────────
# Pick types with cheap, *strong* outcome labels so calibration stays honest
# (CI pass, health check, typecheck) — this is how you sidestep the weak/strong
# label problem for a first integration.
def classify(tool_name: str, tool_input: dict):
    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return "file_edit", "low", 0.8
    if tool_name in ("WebFetch", "WebSearch"):
        return "external_read", "low", 0.8
    if tool_name == "Bash":
        cmd = (tool_input.get("command") or "").lower()
        if "git push" in cmd:
            return "git_push", "high", 0.7          # strong label = CI result
        if any(k in cmd for k in ("vercel deploy", "render deploy", "kubectl apply")):
            return "deploy", "high", 0.65           # strong label = health check
        if any(k in cmd for k in ("rm -rf", "drop table", "git reset --hard", "force")):
            return "destructive_cmd", "high", 0.6
        return "shell_cmd", "medium", 0.75
    return "tool_call", "medium", 0.75


def _key(tool_name, tool_input):
    return hashlib.sha1((tool_name + json.dumps(tool_input, sort_keys=True)).encode()).hexdigest()[:16]


def _ww():
    return WarmWinter(api_key=os.environ["WARMWINTER_API_KEY"],
                      base_url=os.environ.get("WARMWINTER_BASE_URL", "https://api.warmwinter.io"))


def _no_key() -> bool:
    """A hook fires on every tool call — never crash if the key isn't set. Stay
    invisible in shadow; defer to the human in enforce."""
    return not os.environ.get("WARMWINTER_API_KEY")


def pre(event):
    if _no_key():
        return observe() if MODE == "shadow" else emit("ask", "Warm Winter: no API key set.")
    tool_name, tool_input = event["tool_name"], event.get("tool_input", {})
    decision_type, stakes, conf = classify(tool_name, tool_input)
    try:
        d = _ww().decide(
            domain=DOMAIN, decision_type=decision_type, stated_confidence=conf,
            stakes=stakes, candidate_action=tool_name,
            context={"tool": tool_name, "mode": MODE},
            on_ungrounded="escalate",   # no signal yet → ask the human, never fake it
        )
    except WarmWinterError:
        # fail OPEN — never let a gate outage block or rubber-stamp work. In shadow we
        # stay invisible (no decision); in enforce we defer to the human ("ask").
        return observe() if MODE == "shadow" else emit("ask", "Warm Winter unreachable — deferring to you.")

    # remember the decision so `post` can close the loop and the cell calibrates
    book = _load()
    book[_key(tool_name, tool_input)] = d.decision_id
    _save(book)

    # shadow: record only — emit NO permission decision, so Claude Code's normal
    # allow/ask flow is untouched. The cell still learns from the outcome.
    if MODE == "shadow":
        return observe()

    verdict_to_decision = {"act": "allow", "escalate": "ask", "abstain": "ask"}
    reason = f"gate: {d.verdict} · cell {d.cell_state}"
    if d.calibrated_confidence is not None:
        reason += f" · calib {d.calibrated_confidence:.2f}"
    if d.reasons:
        reason += f" · {d.reasons[0]}"
    return emit(verdict_to_decision.get(d.verdict, "ask"), reason)


def post(event):
    if _no_key():
        return
    tool_name, tool_input = event["tool_name"], event.get("tool_input", {})
    book = _load()
    decision_id = book.pop(_key(tool_name, tool_input), None)
    _save(book)
    if not decision_id:
        return
    # WEAK label: did the tool error? Good enough for file_edit/shell_cmd.
    # STRONG label for git_push/deploy comes LATER from CI / a health check — report
    # that from your CI webhook with the same decision_id to truly earn autonomy.
    resp = event.get("tool_response", {})
    errored = bool(resp.get("error")) if isinstance(resp, dict) else False
    try:
        _ww().outcome(decision_id, "failure" if errored else "success",
                      observed={"label_strength": "weak", "source": "tool_exit"})
    except WarmWinterError:
        pass


# ── Claude Code hook plumbing ────────────────────────────────────────────────────
def emit(permission_decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": permission_decision,
        "permissionDecisionReason": reason,
    }}))


def observe():
    """Shadow mode: emit no permission decision. Claude Code proceeds through its
    normal allow/ask flow exactly as if this hook weren't here — we only recorded."""
    return  # printing nothing leaves the permission flow untouched


def _load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save(book):
    json.dump(book, open(STATE, "w"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    event = json.load(sys.stdin)
    (pre if mode == "pre" else post)(event)
