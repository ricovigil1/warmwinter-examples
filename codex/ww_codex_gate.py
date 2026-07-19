#!/usr/bin/env python3
"""Observe Codex tool calls through Warm Winter without changing permissions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from warmwinter import WarmWinter, WarmWinterError

DOMAIN = "agent_ops"
STATE = Path(tempfile.gettempdir()) / "ww_codex_decisions.json"
STRONG_LABEL_TYPES = {"git_push", "deploy"}


def _command(tool_input: dict) -> str:
    return str(tool_input.get("cmd") or tool_input.get("command") or "")


def _segments(command: str) -> list[str]:
    return re.split(r"&&|\|\||[;\n|]", command or "")


def _git_subcommand(segment: str) -> str | None:
    tokens = segment.split()
    while tokens and re.match(r"^\w+=", tokens[0]):
        tokens = tokens[1:]
    if not tokens or tokens[0] != "git":
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            index += 2
        elif token.startswith("-"):
            index += 1
        else:
            return token
    return None


def _head_sha(cwd: str | None) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *( ["-C", cwd] if cwd else [] ), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def classify(tool_name: str, tool_input: dict) -> tuple[str, str, float]:
    if tool_name in ("apply_patch", "Edit", "Write"):
        return "file_edit", "low", 0.8
    if tool_name in ("Bash", "exec_command"):
        command = _command(tool_input)
        segments = _segments(command)
        if any(_git_subcommand(segment) == "push" for segment in segments):
            return "git_push", "high", 0.7
        lowered = command.lower()
        if any(token in lowered for token in ("vercel deploy", "render deploy", "kubectl apply")):
            return "deploy", "high", 0.65
        if any(token in lowered for token in ("rm -rf", "drop table", "git reset --hard", "--force")):
            return "destructive_cmd", "high", 0.6
        return "shell_cmd", "medium", 0.75
    if tool_name.startswith("mcp__"):
        return "mcp_tool", "medium", 0.75
    return "tool_call", "medium", 0.75


def _event_key(event: dict) -> str:
    raw = {
        "session_id": event.get("session_id"),
        "turn_id": event.get("turn_id"),
        "tool_name": event.get("tool_name"),
        "tool_input": event.get("tool_input", {}),
    }
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(book: dict) -> None:
    STATE.write_text(json.dumps(book), encoding="utf-8")


def _client() -> WarmWinter:
    return WarmWinter(
        api_key=os.environ["WARMWINTER_API_KEY"],
        base_url=os.environ.get("WARMWINTER_BASE_URL", "https://api.warmwinter.io"),
        log_verdicts=False,
    )


def pre(event: dict) -> None:
    """Record an advisory decision and emit no Codex permission output."""
    if not os.environ.get("WARMWINTER_API_KEY"):
        return
    tool_name = str(event.get("tool_name") or "tool_call")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    decision_type, stakes, confidence = classify(tool_name, tool_input)
    sha = _head_sha(event.get("cwd")) if decision_type == "git_push" else None
    context = {"tool": tool_name, "surface": "codex", "mode": "shadow"}
    if sha:
        context["commit_sha"] = sha
    try:
        decision = _client().decide(
            domain=DOMAIN,
            decision_type=decision_type,
            stated_confidence=confidence,
            stakes=stakes,
            candidate_action=tool_name,
            context=context,
            idempotency_key=f"codex:gitpush:{sha}" if sha else None,
            on_ungrounded="escalate",
        )
    except (WarmWinterError, OSError):
        return
    book = _load()
    book[_event_key(event)] = decision.decision_id
    _save(book)


def post(event: dict) -> None:
    """Close the loop with a weak tool-execution label."""
    if not os.environ.get("WARMWINTER_API_KEY"):
        return
    book = _load()
    decision_id = book.pop(_event_key(event), None)
    _save(book)
    if not decision_id:
        return
    tool_name = str(event.get("tool_name") or "tool_call")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    decision_type, _, _ = classify(tool_name, tool_input)
    if decision_type in STRONG_LABEL_TYPES:
        return
    response = event.get("tool_response")
    errored = bool(response.get("error")) if isinstance(response, dict) else False
    try:
        _client().outcome(
            decision_id,
            "failure" if errored else "success",
            observed={"label_strength": "weak", "source": "codex_tool_exit"},
        )
    except (WarmWinterError, OSError):
        pass


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre"
    event = json.load(sys.stdin)
    (pre if phase == "pre" else post)(event)


if __name__ == "__main__":
    main()
