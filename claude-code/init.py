#!/usr/bin/env python3
"""
warmwinter init — wire the Warm Winter gate into Claude Code in one command.

Collapses the manual setup (copy the hook somewhere stable, find your interpreter, merge
the PreToolUse/PostToolUse hooks into settings.json, set the key + shadow mode) into:

    python init.py --key ww_xxx            # global: gate every Claude Code session
    python init.py --key ww_xxx --scope project    # only this repo
    python init.py --key ww_xxx --dry-run          # show what it would write, change nothing

Mint a key first at https://www.warmwinter.io (or /api/v1/gate/keys). Defaults to SHADOW
mode (observe only — records cells, never blocks); flip to enforce later once cells verify.
Restart Claude Code afterward so it loads the new settings.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
HOOK_DIR = Path.home() / ".warmwinter" / "hook"   # stable copy (survives git branch switches)
HOOK_FILE = HOOK_DIR / "ww_claude_code_gate.py"
HERE = Path(__file__).resolve().parent


def _settings_paths(scope: str):
    if scope == "global":
        base = Path.home() / ".claude"
        return base / "settings.json", base / "settings.json"   # env lives in same file (home, private)
    base = Path.cwd() / ".claude"
    return base / "settings.json", base / "settings.local.json"  # key in the gitignored local file


def _hook_entry(py: str, mode: str):
    cmd = f'"{py}" "{HOOK_FILE}"'
    return {"matcher": MATCHER, "hooks": [{"type": "command", "command": f"{cmd} %s"}]}


def _has_ours(entries):
    return any("ww_claude_code_gate.py" in h.get("command", "")
               for e in entries for h in e.get("hooks", []))


def main():
    ap = argparse.ArgumentParser(prog="warmwinter init")
    ap.add_argument("--key", default=os.environ.get("WARMWINTER_API_KEY"),
                    help="your gate API key (or set WARMWINTER_API_KEY)")
    ap.add_argument("--scope", choices=("global", "project"), default="global")
    ap.add_argument("--mode", choices=("shadow", "enforce"), default="shadow")
    ap.add_argument("--base-url", default="https://api.warmwinter.io")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.key:
        sys.exit("No key. Mint one at https://www.warmwinter.io, then: init.py --key ww_...")
    try:
        import warmwinter  # noqa: F401
    except ImportError:
        print("note: the 'warmwinter' package isn't importable here — run `pip install warmwinter`\n"
              "      in the interpreter the hook will use (below).", file=sys.stderr)

    py = sys.executable.replace("\\", "/")
    hooks_path, env_path = _settings_paths(args.scope)

    # 1) stable copy of the hook (so checking out a git branch can't break the live hook)
    plan = [f"copy hook → {HOOK_FILE}"]
    if not args.dry_run:
        HOOK_DIR.mkdir(parents=True, exist_ok=True)
        for f in ("ww_claude_code_gate.py", "check_progress.py"):
            if (HERE / f).exists():
                shutil.copy2(HERE / f, HOOK_DIR / f)

    # 2) merge the hooks into settings.json
    settings = json.loads(hooks_path.read_text()) if hooks_path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    for event in ("PreToolUse", "PostToolUse"):
        arr = hooks.setdefault(event, [])
        if _has_ours(arr):
            plan.append(f"{hooks_path.name}: {event} hook already present — leaving it")
            continue
        mode_arg = "pre" if event == "PreToolUse" else "post"
        arr.append(_hook_entry(py, args.mode))
        arr[-1]["hooks"][0]["command"] = arr[-1]["hooks"][0]["command"] % mode_arg
        plan.append(f"{hooks_path.name}: add {event} hook")

    # 3) env (key/mode/base) — in the home settings (global) or the gitignored local file (project)
    env_settings = settings if env_path == hooks_path else (
        json.loads(env_path.read_text()) if env_path.exists() else {})
    env = env_settings.setdefault("env", {})
    env.update({"WARMWINTER_API_KEY": args.key, "WARMWINTER_BASE_URL": args.base_url,
                "WW_GATE_MODE": args.mode, "PYTHONUTF8": "1"})
    plan.append(f"{env_path.name}: set WARMWINTER_API_KEY + WW_GATE_MODE={args.mode}")

    if args.dry_run:
        print("DRY RUN — would do:\n  " + "\n  ".join(plan))
        print(f"\nhooks → {hooks_path}\nenv   → {env_path}\ninterpreter: {py}")
        return

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(json.dumps(settings, indent=2))
    if env_path != hooks_path:
        env_path.write_text(json.dumps(env_settings, indent=2))
        # keep the key out of git
        gi = Path.cwd() / ".gitignore"
        line = ".claude/settings.local.json"
        if not gi.exists() or line not in gi.read_text():
            with gi.open("a") as f:
                f.write(f"\n# Warm Winter local key\n{line}\n")

    print("✓ Warm Winter gate wired.\n  " + "\n  ".join(plan))
    print(f"\nMode: {args.mode}" + ("  (observe only — never blocks)" if args.mode == "shadow" else ""))
    print("Next: restart Claude Code, then code as usual.")
    print(f"Watch it learn:  WARMWINTER_API_KEY={args.key[:8]}… \"{py}\" \"{HOOK_DIR / 'check_progress.py'}\"")


if __name__ == "__main__":
    main()
