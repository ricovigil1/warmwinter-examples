# Observe Codex with Warm Winter

This recipe connects Codex's supported lifecycle hooks to Warm Winter. It
records local tool decisions and execution outcomes so your
`agent_ops x decision_type` cells can calibrate from real work.

It is deliberately **shadow-only**:

- Codex's sandbox, approvals, and hook-trust review remain authoritative.
- Warm Winter emits no allow, block, or rewrite instruction.
- A Warm Winter or network failure never interrupts Codex.
- Prompts, file contents, command output, and tool responses are not sent to
  Warm Winter. The API receives decision coordinates and gate metadata only.

## Setup

1. Install the SDK and mint a free key from the
   [Warm Winter dashboard](https://www.warmwinter.io/signup):

   ```bash
   pip install warmwinter
   export WARMWINTER_API_KEY=ww_your_key
   ```

2. Copy `ww_codex_gate.py` to a stable location.
3. Copy `hooks.snippet.json` to either:

   - `~/.codex/hooks.json` for every trusted project, or
   - `.codex/hooks.json` inside one trusted repository.

4. Replace both absolute-path placeholders with the script's absolute path.
5. Restart Codex, open `/hooks`, review the exact command, and trust it.

Codex requires trust again if the hook definition changes. Project-local hooks
run only for trusted projects.

## What gets graded

| Codex tool | Warm Winter cell | Stakes | Outcome |
|---|---|---:|---|
| `apply_patch`, `Edit`, `Write` | `file_edit` | low | weak: tool completed |
| ordinary `Bash` / `exec_command` | `shell_cmd` | medium | weak: command completed |
| `git push` | `git_push` | high | left open; CI supplies the strong label by commit SHA |
| deploy commands | `deploy` | high | left open; deployed health supplies the strong label |
| destructive commands | `destructive_cmd` | high | weak: command completed |
| MCP tools | `mcp_tool` | medium | weak: tool completed |

Tool-exit labels only answer “did it run?”, not “was it the right judgment?”
Use CI, deploy health, or human review as strong labels for consequential cells.

## Coverage limits

Codex lifecycle hooks cover local function tools such as shell commands,
`apply_patch`, and MCP tools. Hosted tools such as web search do not pass
through the local hook path. Treat this as an observation layer, not a complete
enforcement boundary.
