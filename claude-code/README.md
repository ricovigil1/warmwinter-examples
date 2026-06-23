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
python init.py --key ww_your_key        # mint a key at https://www.warmwinter.io
# add --scope project to gate only this repo; --dry-run to preview; defaults to shadow
```

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
  That's fine for `file_edit`/`shell_cmd`. For `git_push`/`deploy`, the *strong*
  label is "did CI / the health check pass?" — report that from your CI webhook
  with the same `decision_id` to let those cells truly earn autonomy. Don't grant
  autonomy on "was this the *right* change" (needs human review) until you've got a
  strong signal for it.
- **Confidence:** the hook can't read the model's internal confidence, so it uses a
  per-type prior. A deeper integration would have the agent emit its own
  `stated_confidence`.
