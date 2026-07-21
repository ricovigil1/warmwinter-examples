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
import re
import json
import hashlib
import tempfile
import subprocess

# the published SDK: `pip install warmwinter`
from warmwinter import WarmWinter, WarmWinterError

STATE = os.path.join(tempfile.gettempdir(), "ww_gate_decisions.json")
DOMAIN = "agent_ops"
MODE = os.environ.get("WW_GATE_MODE", "shadow").lower()   # shadow (observe) | enforce

# Types whose REAL outcome arrives later, from elsewhere (CI, a health check) — not
# from the tool's own exit code. We leave these OPEN in `post` so the strong label
# can resolve them by commit SHA via /gate/outcome/by-ref. Weak-labeling them on
# tool-exit would cement "the push didn't error" before CI ever reports, and
# /outcome is idempotent — the first (weak) label wins. So: don't weak-label these.
STRONG_LABEL_TYPES = {"git_push", "pr_merge", "deploy"}


def _repo_dir_from_cmd(command: str):
    """The dir the push actually runs in. An agent invokes a push as `cd <dir> &&
    git push` (or `git -C <dir> push`), but the hook is a SEPARATE process whose own
    cwd is the Claude Code session dir — frequently NOT the repo being pushed (and
    often not a repo at all). So parse the target dir out of the command instead of
    trusting the hook's cwd. Without this, HEAD resolves to nothing, the decision is
    minted with no commit_sha, and CI can never join back to it via /outcome/by-ref —
    the git_push cell can then never verify."""
    m = (re.search(r'git\s+-C\s+("[^"]+"|\'[^\']+\'|\S+)', command or "")
         or re.search(r'(?:^|;|&&|\|\|)\s*cd\s+("[^"]+"|\'[^\']+\'|\S+)', command or ""))
    if not m:
        return None
    d = m.group(1).strip('"\'')
    if d.startswith("~"):
        d = os.path.expanduser(d)
    # MSYS/Git-Bash path (/c/Users/...) → Windows drive path (C:/Users/...) so a
    # native git.exe accepts it; a no-op on POSIX where paths already start with /.
    return re.sub(r'^/([a-zA-Z])/', lambda x: x.group(1).upper() + ':/', d)


def _head_sha(command: str = ""):
    """The commit being pushed — the join key CI will report back on. Best-effort:
    a hook must never crash, so any git failure just means no SHA (weak fallback).
    Resolves HEAD in the repo the push runs in (see _repo_dir_from_cmd), not the
    hook's own cwd."""
    d = _repo_dir_from_cmd(command)
    args = ["git"] + (["-C", d] if d else []) + ["rev-parse", "HEAD"]
    try:
        return subprocess.check_output(
            args, text=True, stderr=subprocess.DEVNULL).strip() or None
    except Exception:
        return None


# ── classify a tool call into (decision_type, stakes, confidence) ────────────────
# Pick types with cheap, *strong* outcome labels so calibration stays honest
# (CI pass, health check, typecheck) — this is how you sidestep the weak/strong
# label problem for a first integration.
#
# Confidence is a predictor, not a constant. The weak-label outcome is "did the
# tool error?", so `confidence` is an honest prior on P(this specific action exits
# clean). It MUST vary with the action: a constant confidence puts every outcome in one
# calibration bin, which gives a cell zero resolution (no skill over the base rate) — so
# it can never earn `verified`, and the gate is right to refuse it. By scoring each action
# on real signal (read-only vs install vs search; Write vs Edit; search vs fetch) the cell
# gets genuine discrimination (resolution); the gate's recalibrator then maps these priors
# to true rates (calibration). These are deliberately NOT fit to the observed data — they're
# domain priors the gate validates against outcomes. Treat these example values as
# illustrative seeds and fit deployment-specific priors from honest outcome data.

def _shell_confidence(cmd: str) -> float:
    """Honest prior that a shell command exits 0, from what the command actually is."""
    c = cmd.strip().lower()
    fragile = ("npm install", "npm ci", "pnpm", "yarn ", "pip install", "uv pip",
               "apt ", "apt-get", "brew ", "curl ", "wget ", "git fetch", "git pull",
               "git clone", "docker build", "docker run", "make ", "cargo build", "go build")
    read_only = ("ls", "pwd", "echo ", "cat ", "head ", "tail ", "wc ", "stat ",
                 "which ", "whoami", "date", "printenv", "git status", "git log",
                 "git diff", "git branch", "git remote", "git show", "cd ")
    search_test = ("grep", "rg ", "find ", "pytest", "npm test", "go test", "jest",
                   "ruff", "mypy", "tsc", "eslint", "test ", "[ ")
    if any(k in c for k in fragile):                     # network / build — genuinely flaky
        return 0.62
    if any(c.startswith(k) for k in read_only):          # near-deterministic reads
        return 0.97
    if any(k in c for k in search_test):                 # exit nonzero by design (no match / fail)
        return 0.74
    return 0.88                                          # ordinary shell — usually fine


def _edit_confidence(tool_name: str, ti: dict) -> float:
    """P(a file edit applies clean). Write/create rarely errors; Edit can miss its
    match, more so the longer/more numerous the match."""
    if tool_name == "Write":
        return 0.95
    if tool_name == "NotebookEdit":
        return 0.85
    if tool_name == "MultiEdit":
        return 0.80                                      # several matches, any can miss
    old = ti.get("old_string") or ""                     # Edit: longer match = likelier miss
    return 0.86 if len(old) <= 240 else 0.78


# Classify on what a segment actually INVOKES, not on substrings. `grep "git push"`,
# `echo "run git push later"`, and `git commit -m "…git push…"` must NOT count as
# pushes — a misclassified push opens a strong-label decision that never resolves
# (it has no CI), quietly polluting the git_push cell's coverage. So split into
# pipeline/operator segments and inspect each segment's leading program.

def _segments(command: str):
    """Pipeline/operator segments of a shell command (`a && b | c` → [a, b, c])."""
    return re.split(r'&&|\|\||[;\n|]', command or "")


def _lead_tokens(segment: str):
    """A segment's leading program + args, skipping any `VAR=val` env prefixes."""
    toks = segment.split()
    while toks and re.match(r'^\w+=', toks[0]):
        toks = toks[1:]
    return toks


def _git_subcommand(segment: str):
    """If the segment INVOKES git, its subcommand (e.g. 'push'), skipping git's
    global options and the args they consume (-C <dir>, -c <cfg>). Else None."""
    toks = _lead_tokens(segment)
    if not toks or toks[0] != "git":
        return None
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            i += 2                                   # option consumes its argument
        elif t.startswith("-"):
            i += 1
        else:
            return t
    return None


def _is_pr_merge(segment: str) -> bool:
    """True only when the segment actually invokes `gh pr merge`."""
    toks = _lead_tokens(segment)
    return len(toks) >= 3 and toks[:3] == ["gh", "pr", "merge"]


def _pr_merge_confidence(segment: str) -> float:
    """Prior on P(the merged revision clears its downstream checks).

    This is deliberately feature-derived instead of a constant: auto-merge waits
    for branch requirements, match-head-commit protects against a stale review,
    while --admin explicitly bypasses protections. The realized CI/deploy outcome
    remains the judge and recalibrates these priors over time.
    """
    toks = _lead_tokens(segment)
    if "--admin" in toks:
        return 0.45
    if "--match-head-commit" in toks:
        return 0.86
    if "--auto" in toks:
        return 0.82
    return 0.68


def classify(tool_name: str, tool_input: dict):
    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return "file_edit", "low", _edit_confidence(tool_name, tool_input)
    if tool_name in ("WebFetch", "WebSearch"):
        # WebSearch almost always returns; WebFetch can 404 / time out / redirect / 999.
        return "external_read", "low", (0.93 if tool_name == "WebSearch" else 0.78)
    if tool_name == "Bash":
        raw = tool_input.get("command") or ""
        segs = _segments(raw)
        merge = next((s for s in segs if _is_pr_merge(s)), None)
        if merge is not None:
            return "pr_merge", "high", _pr_merge_confidence(merge)
        if any(_git_subcommand(s) == "push" for s in segs):
            return "git_push", "high", 0.7          # strong label = CI result
        leads = [tuple(_lead_tokens(s)[:2]) for s in segs]
        if any(l in {("vercel", "deploy"), ("render", "deploy"), ("kubectl", "apply")}
               for l in leads):
            return "deploy", "high", 0.65           # strong label = health check
        low = raw.lower()
        if (any(_git_subcommand(s) == "reset" and "--hard" in s for s in segs)
                or "rm -rf" in low or "drop table" in low or "--force" in low):
            return "destructive_cmd", "high", 0.6
        return "shell_cmd", "medium", _shell_confidence(low)
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
    # Stamp the commit SHA so CI can resolve this exact decision later (strong label).
    # idempotency_key on the SHA makes a re-push of the same commit replay, not double-open.
    cmd_str = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    sha = _head_sha(cmd_str) if decision_type in STRONG_LABEL_TYPES else None
    ctx = {"tool": tool_name, "mode": MODE}
    if sha:
        ctx["commit_sha"] = sha
    try:
        d = _ww().decide(
            domain=DOMAIN, decision_type=decision_type, stated_confidence=conf,
            stakes=stakes, candidate_action=tool_name, context=ctx,
            idempotency_key=(f"{decision_type}:{sha}" if sha else None),
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
    # Strong-label types are resolved LATER, by CI/health-check via /outcome/by-ref
    # (see STRONG_LABEL_TYPES). Leave them OPEN — a weak tool-exit label here would
    # win idempotently and the cell could never verify on the real result.
    decision_type, _, _ = classify(tool_name, tool_input)
    if decision_type in STRONG_LABEL_TYPES:
        return
    # WEAK label: did the tool error? Honest for types where the exit IS the outcome
    # (file_edit/shell_cmd/external_read).
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
