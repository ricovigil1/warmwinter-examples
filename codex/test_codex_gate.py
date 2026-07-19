import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ww_codex_gate", HERE / "ww_codex_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class FakeClient:
    def __init__(self):
        self.decides = []
        self.outcomes = []

    def decide(self, **kwargs):
        self.decides.append(kwargs)
        return SimpleNamespace(decision_id="decision-1")

    def outcome(self, *args, **kwargs):
        self.outcomes.append((args, kwargs))


class CodexGateTests(unittest.TestCase):
    def setUp(self):
        self.old_key = os.environ.get("WARMWINTER_API_KEY")
        os.environ["WARMWINTER_API_KEY"] = "ww_test"
        self.tmp = tempfile.TemporaryDirectory()
        gate.STATE = Path(self.tmp.name) / "state.json"
        self.client = FakeClient()
        gate._client = lambda: self.client

    def tearDown(self):
        self.tmp.cleanup()
        if self.old_key is None:
            os.environ.pop("WARMWINTER_API_KEY", None)
        else:
            os.environ["WARMWINTER_API_KEY"] = self.old_key

    def test_classifies_codex_tools(self):
        self.assertEqual(gate.classify("apply_patch", {})[:2], ("file_edit", "low"))
        self.assertEqual(gate.classify("Bash", {"cmd": "git push origin main"})[:2],
                         ("git_push", "high"))
        self.assertEqual(gate.classify("mcp__github__get_issue", {})[:2],
                         ("mcp_tool", "medium"))

    def test_pre_and_post_close_the_loop(self):
        event = {
            "session_id": "s1",
            "turn_id": "t1",
            "tool_name": "Bash",
            "tool_input": {"cmd": "npm test"},
        }
        gate.pre(event)
        self.assertEqual(len(self.client.decides), 1)
        self.assertTrue(gate.STATE.exists())

        gate.post({**event, "tool_response": {"output": "ok"}})
        self.assertEqual(len(self.client.outcomes), 1)
        self.assertEqual(self.client.outcomes[0][0][1], "success")

    def test_missing_key_is_invisible(self):
        os.environ.pop("WARMWINTER_API_KEY", None)
        gate.pre({"tool_name": "Bash", "tool_input": {"cmd": "echo hi"}})
        self.assertEqual(self.client.decides, [])


if __name__ == "__main__":
    unittest.main()
