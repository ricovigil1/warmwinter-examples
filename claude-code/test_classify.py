#!/usr/bin/env python3
"""Standalone check for the hook's command classifier.

The classifier decides which strong-label bucket a Bash command falls in. The
subtle bug it guards against: a command that merely MENTIONS `git push` (a grep
pattern, an echo, a commit message) must not be logged as a real push — a
misclassified push opens a strong-label decision that never resolves (no CI ever
runs for it), quietly polluting the git_push cell's coverage. Run: `python
test_classify.py` (no deps; stubs the SDK import).
"""
import importlib.util
import os
import sys
import types

sys.modules.setdefault(
    "warmwinter", types.SimpleNamespace(WarmWinter=object, WarmWinterError=Exception))
_spec = importlib.util.spec_from_file_location(
    "wwhook", os.path.join(os.path.dirname(__file__), "ww_claude_code_gate.py"))
_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook)


def cls(cmd):
    return _hook.classify("Bash", {"command": cmd})[0]


def confidence(cmd):
    return _hook.classify("Bash", {"command": cmd})[2]


CASES = {
    # Mentions of "git push" that are NOT invocations → plain shell_cmd.
    "grep -oh '\"command\":\"[^\"]*git push[^\"]*\"' *.jsonl": "shell_cmd",
    'echo "run git push later" && ls': "shell_cmd",
    'git commit -m "reminder: git push after CI"': "shell_cmd",
    "grep -c 'git push' *.jsonl | head": "shell_cmd",
    # Real pushes, including the shapes an agent actually emits.
    "cd /c/Users/x/repo && git push origin main 2>&1 | tail -3": "git_push",
    "git push -u origin feat/observatory-operator": "git_push",
    "git -C /repo push origin main": "git_push",
    "git push --force-with-lease": "git_push",
    # A PR merge is a distinct high-stakes decision. In this repository it can
    # trigger production, so it must not disappear into the generic shell cell.
    "gh pr merge 44 --merge --delete-branch": "pr_merge",
    "cd /repo && gh pr merge --squash": "pr_merge",
    "echo 'gh pr merge after approval'": "shell_cmd",
    "grep -R 'gh pr merge' docs": "shell_cmd",
    # Deploy: real leading invocation only, not a mention.
    "vercel deploy --prod": "deploy",
    "render deploy": "deploy",
    "echo 'vercel deploy'": "shell_cmd",
    # Destructive: anchored, and 'enforce' must NOT trip the old 'force' substring.
    "rm -rf build && npm run build": "destructive_cmd",
    "git reset --hard origin/main": "destructive_cmd",
    "npm run enforce-lint": "shell_cmd",
    # Other tools keep their buckets.
}


def main():
    failures = []
    for cmd, want in CASES.items():
        got = cls(cmd)
        status = "PASS" if got == want else "FAIL"
        if got != want:
            failures.append((cmd, want, got))
        print(f"  {status}  {got:15s} (want {want:15s})  <- {cmd[:64]}")
    # Non-Bash tools.
    assert _hook.classify("Write", {})[0] == "file_edit"
    assert _hook.classify("WebFetch", {})[0] == "external_read"
    assert confidence("gh pr merge 44 --admin") < confidence("gh pr merge 44")
    assert confidence("gh pr merge 44 --auto") > confidence("gh pr merge 44")
    assert confidence("gh pr merge 44 --match-head-commit abc") > confidence("gh pr merge 44")

    # Every deferred strong-label type needs the commit join key. Otherwise the
    # later CI/health verifier has no durable way to resolve the open decision.
    captured = {}
    class FakeGate:
        def decide(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(decision_id="dec_test")
    _hook._head_sha = lambda _command: "abc123"
    _hook._ww = lambda: FakeGate()
    _hook._no_key = lambda: False
    _hook._load = lambda: {}
    _hook._save = lambda _book: None
    _hook.pre({"tool_name": "Bash", "tool_input": {"command": "render deploy"}})
    assert captured["context"]["commit_sha"] == "abc123"
    assert captured["idempotency_key"] == "deploy:abc123"

    print("\n" + ("ALL CLASSIFY CHECKS PASSED" if not failures
                  else f"{len(failures)} FAILURE(S): {failures}"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
