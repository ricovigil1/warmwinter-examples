# Gate a Claude Code agent through Warm Winter

Let an AI coding agent decide *for itself* which of its actions are safe to run
unattended — and earn that autonomy from real outcomes, instead of asking you to
approve everything forever.

## How it works

A `PreToolUse` hook fires before every tool call. It asks the Warm Winter gate
`act | escalate | abstain`, which maps to Claude Code's `allow | ask | ask`:

```
agent wants to run a tool
  → PreToolUse hook → POST /api/v1/gate/decide { decision_type, stakes, ... }
       act      → allow   (run autonomously)
       escalate → ask     (check with you)
       abstain  → ask     ("no grounded signal here — you decide")
  → tool runs → PostToolUse hook → POST /api/v1/gate/outcome (success/failure)
  → the (domain × decision_type) cell recalibrates
```

At **cold start every cell is ungrounded.** So don't let the gate steer yet — start
in **shadow mode** (the default): the hook *records* every decision and outcome but
emits no permission decision, leaving Claude Code's normal allow/ask flow untouched.
**Zero friction, but the cells calibrate from your real work.** After ~1–2 weeks the
`git_push` / `deploy` cells (which have strong CI/health labels) move to `verified`;
*then* flip `WW_GATE_MODE=enforce` and the gate starts auto-allowing what it has
earned. **The prompts shrink as trust is earned — but only after it's earned.**

## Setup — one command

```bash
pip install warmwinter
python init.py --device                 # approve in your browser — nothing to paste
# or:  python init.py --key ww_your_key  (mint a key at https://www.warmwinter.io)
# add --scope project to gate only this repo; --dry-run to preview; defaults to shadow
```

`--device` starts a keyless flow: it prints a link, you approve it in your logged-in
browser at `/activate`, and the key is minted and handed straight to the installer — no
secret on your clipboard.

`init.py` copies the hook to a stable location, finds your interpreter, merges the
`PreToolUse`/`PostToolUse` hooks into your `.claude/settings.json`, and sets the key +
shadow mode. It's idempotent (safe to re-run) and keeps the key out of git for project
scope. **Restart Claude Code afterward** so it loads the settings, then just code —
watch the frontier fill with `python check_progress.py`. Flip `WW_GATE_MODE=enforce`
once the cells you care about reach `verified`.

<details><summary>Manual setup (if you'd rather not run the installer)</summary>

1. `pip install warmwinter`; mint a key at `/api/v1/gate/keys`; export `WARMWINTER_API_KEY`.
   (Hosted API `https://api.warmwinter.io`; override with `WARMWINTER_BASE_URL`.)
2. Merge `settings.snippet.json` into your `.claude/settings.json` (fix the path).
3. Leave `WW_GATE_MODE` unset (= shadow); flip to `enforce` when ready.
</details>

## Honesty notes (read these)

- **Cost:** the gate has no LLM in it — each decision is a cell lookup, so this is
  effectively free against your own deployment. `escalate` = "ask the human", not
  "spend more compute".
- **Fails open:** if the gate is unreachable the hook never blocks or rubber-stamps —
  in `enforce` it returns `ask`; in `shadow` it stays invisible (your normal flow runs).
- **Weak vs. strong labels:** `post` reports a *weak* label (did the tool error?).
  That's appropriate for `file_edit`/`shell_cmd`, where the exit is the immediate
  result. A successful `git_push`, `pr_merge`, or `deploy` command does **not** prove
  the revision was good, so those decisions stay open until a strong verifier closes
  them by commit SHA:
  - **push → CI:** copy [`strong_label_ci.yml`](strong_label_ci.yml) into
    `.github/workflows/warmwinter-strong-label.yml` and name your real CI workflow;
  - **merge → verifier:** run [`verify_and_label.py`](verify_and_label.py) with the
    repository's required smoke/build command;
  - **deploy → live health:** run [`deploy_health_label.py`](deploy_health_label.py)
    after deploy; it requires the target commit to be live and stable.

  These paths pass `decision_type` as well as the SHA, so push, merge, and deploy
  decisions for one revision cannot cross-resolve. Don't grant
  autonomy on "was this the *right* change" (needs human review) until you've got a
  strong signal for it.
- **Confidence:** the hook cannot read the model's internal confidence. It derives a
  varying prior from observable action features instead of sending one constant for
  every call; real outcomes still recalibrate that prior. A deeper integration can
  supply the agent's own `stated_confidence`.
