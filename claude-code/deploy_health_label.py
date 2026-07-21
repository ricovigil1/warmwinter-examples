#!/usr/bin/env python3
"""Strong-label a DEPLOY from a post-deploy health check.

The companion to the CI strong-label (strong_label_ci.yml). The Claude Code gate
hook opens a `deploy` decision (left OPEN, stamped with the commit SHA) whenever the
agent runs a deploy command. This script closes that loop with the STRONG label:
did the new revision actually go live and stay healthy?

What "healthy" means here (honest by construction):
  1. The deployed commit is ACTUALLY live — we poll /health until it reports the
     target SHA (Render injects RENDER_GIT_COMMIT, surfaced on /health). A healthy
     response from the OLD revision does not count as a successful deploy.
  2. It STAYS healthy — /health must return 200 + status:ok on every poll across a
     short settle window, not just once. A deploy that flaps is a failure.
Timeout or any unhealthy poll → failure label. That negative is exactly what the
`deploy` cell needs to calibrate; a deploy that silently broke the service must NOT
look successful.

Resolves via /gate/outcome/by-ref with decision_type="deploy" so it never cross-
resolves the git_push decision for the same commit.

Usage (from CI or a Render post-deploy job):
    WARMWINTER_API_KEY=ww_...  python deploy_health_label.py \
        --health-url https://api.warmwinter.io/health \
        --commit "$GIT_SHA"

Env fallbacks: WARMWINTER_API_KEY, WARMWINTER_BASE_URL, WW_HEALTH_URL, GIT_COMMIT.
Exit code is 0 whether the deploy passed or failed (reporting succeeded); it is
non-zero only if it couldn't reach the gate to report at all — so this never fails
your pipeline for an honest "deploy failure" label.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from warmwinter import WarmWinter, WarmWinterError


def _poll_health(url: str, timeout: float):
    """Return (live_commit, healthy_bool) for one probe, or (None, False) on error."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = json.loads(r.read().decode() or "{}")
            healthy = r.status == 200 and body.get("status") == "ok"
            return body.get("commit"), healthy
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None, False


def check_deploy(health_url: str, commit: str, *, window_s: float, interval_s: float,
                 require_commit: bool) -> tuple[bool, dict]:
    """Poll until the target commit is live, then confirm it stays healthy across the
    window. Returns (success, observed)."""
    deadline = time.time() + window_s
    saw_commit = False
    healthy_streak = 0
    polls = 0
    last_commit = None
    # Wait for the new revision to come up (commit matches).
    while time.time() < deadline:
        last_commit, healthy = _poll_health(health_url, timeout=interval_s)
        polls += 1
        commit_ok = (not require_commit) or (last_commit is not None
                                             and last_commit.startswith(commit[:12]))
        if commit_ok and healthy:
            saw_commit = True
            healthy_streak += 1
            # Require a few consecutive healthy polls so a flapping deploy fails.
            if healthy_streak >= 3:
                return True, {"polls": polls, "live_commit": last_commit,
                              "healthy_streak": healthy_streak, "phase": "stable"}
        else:
            healthy_streak = 0
        time.sleep(interval_s)
    observed = {"polls": polls, "live_commit": last_commit, "saw_target_commit": saw_commit,
                "healthy_streak": healthy_streak,
                "reason": ("commit never went live" if not saw_commit
                           else "did not stay healthy for the settle window")}
    return False, observed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--health-url", default=os.environ.get("WW_HEALTH_URL"))
    ap.add_argument("--commit", default=os.environ.get("GIT_COMMIT"))
    ap.add_argument("--window", type=float, default=float(os.environ.get("WW_DEPLOY_WINDOW", "180")))
    ap.add_argument("--interval", type=float, default=float(os.environ.get("WW_DEPLOY_INTERVAL", "5")))
    ap.add_argument("--no-require-commit", action="store_true",
                    help="don't insist /health echoes the target commit (use if RENDER_GIT_COMMIT is unset)")
    args = ap.parse_args()

    if not args.health_url or not args.commit:
        print("need --health-url and --commit (or WW_HEALTH_URL / GIT_COMMIT)", file=sys.stderr)
        return 2
    if not os.environ.get("WARMWINTER_API_KEY"):
        print("WARMWINTER_API_KEY not set — nothing to report to.", file=sys.stderr)
        return 0  # not a failure of the deploy; just nothing to record

    success, observed = check_deploy(
        args.health_url, args.commit, window_s=args.window, interval_s=args.interval,
        require_commit=not args.no_require_commit)
    observed.update({"health_url": args.health_url, "source": "deploy_health_check"})
    print(("PASS" if success else "FAIL") + f" deploy {args.commit[:12]} — {observed}")

    ww = WarmWinter(api_key=os.environ["WARMWINTER_API_KEY"],
                    base_url=os.environ.get("WARMWINTER_BASE_URL", "https://api.warmwinter.io"))
    try:
        res = ww.outcome_by_ref(args.commit, "success" if success else "failure",
                                observed=observed, decision_type="deploy")
        print("recorded:", res)
    except WarmWinterError as e:
        # 404 = no open deploy decision for this SHA (deploy wasn't gated) → fine.
        if getattr(e, "status", None) == 404:
            print("· no open deploy decision for this commit — nothing to label")
            return 0
        print(f"could not report to the gate: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

