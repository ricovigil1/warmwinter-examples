#!/usr/bin/env python3
"""Run a real verifier and strong-label an open Gate decision by commit SHA.

This is the provider-independent fallback for CI outages or exhausted hosted
runner minutes. It never treats a successful push or merge command as proof.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from warmwinter import WarmWinter, WarmWinterError


def _commit(ref: str) -> str:
    if ref.upper() != "HEAD":
        return ref
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
    ).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", required=True, help="commit SHA or HEAD")
    ap.add_argument("--decision-type", choices=("git_push", "pr_merge", "deploy"),
                    default="git_push")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("provide a verifier after --")
    if not os.environ.get("WARMWINTER_API_KEY"):
        print("WARMWINTER_API_KEY is required", file=sys.stderr)
        return 2

    sha = _commit(args.commit)
    print("verifying:", " ".join(command))
    completed = subprocess.run(command, shell=False)
    outcome = "success" if completed.returncode == 0 else "failure"
    observed = {"label_strength": "strong", "source": "local_verifier",
                "verifier": command[0], "exit_code": completed.returncode}
    ww = WarmWinter(
        api_key=os.environ["WARMWINTER_API_KEY"],
        base_url=os.environ.get("WARMWINTER_BASE_URL", "https://api.warmwinter.io"),
    )
    try:
        result = ww.outcome_by_ref(
            sha, outcome, observed=observed, decision_type=args.decision_type)
        print("recorded:", result)
    except WarmWinterError as exc:
        if getattr(exc, "status", None) == 404:
            print("no open decision for this commit and type", file=sys.stderr)
        else:
            print(f"could not report to the Gate: {exc}", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

