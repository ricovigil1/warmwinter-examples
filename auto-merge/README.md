# Auto-merge gate

Should an agent's pull request merge **unsupervised**, or pause for a human?

This example gates `git`'s most irreversible everyday action with Warm Winter. In
CI, after your checks run, it asks the gate — given how confident the checks are —
whether this PR is trustworthy enough to auto-merge. Only an `act` verdict enables
auto-merge; anything else holds the PR for review. After the PR lands, a follow-up
reports whether `main` stayed green, so the `auto_merge` cell learns from the real
outcome instead of a guess.

## Files

- **`gate_merge.py`** — calls `decide(domain="agent", decision_type="auto_merge", …)`
  with a confidence signal you trust, at `stakes="high"`, `on_ungrounded="abstain"`.
- **`auto-merge-gate.yml`** — the GitHub Actions workflow. **Copy it into
  `.github/workflows/` in your own repo** and add a `WARMWINTER_API_KEY` secret.
- **`report_outcome.py`** — closes the loop: report `success`/`failure` after the
  merge so the cell calibrates.

## The honest part

The gate **advises** — the workflow makes the merge call. And it only earns trust
it has *measured*: a brand-new `auto_merge` cell is seeded but ungrounded, so at
high stakes it abstains (asks a human) until enough real outcomes land. That's the
point — it would rather say "not this one" than rubber-stamp.

> Tip: point `CI_CONFIDENCE` at a signal you'd actually stake the repo on — passing
> required checks, a coverage floor, an eval score. Inflating it just teaches the
> gate the wrong thing; it's calibrated against what actually happens.
