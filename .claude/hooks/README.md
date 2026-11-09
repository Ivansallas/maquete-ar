# Hooks — Real Enforcement

Prose rules in CLAUDE.md are context, not enforcement. The hook configured in
`.claude/settings.json` is a hard gate.

## What is active

`PreToolUse` on the `Bash` and `PowerShell` tools runs
`.claude/hooks/pre_commit_check.py`. If the command contains `git commit` or
`git push`, it runs, in order:

1. `ruff check .` (lint)
2. `mypy` (types, config in `pyproject.toml`)
3. `pytest -q` (tests)

If any fails, the hook exits with code **2**, which blocks the tool call and
sends the error output back to Claude to fix. Any other command passes through
(exit 0).

## Implementation notes

- Claude Code passes the tool call as **JSON on stdin** (`tool_input.command`),
  not as an environment variable. Only **exit code 2** blocks; exit 1 is a
  non-blocking error. (The generic kit example used `$CLAUDE_TOOL_INPUT` and
  `exit 1`, which would never block.)
- The script uses the project's `.venv` Python if present.
- Test it manually:
  `echo '{"tool_input":{"command":"git commit -m x"}}' | python .claude/hooks/pre_commit_check.py; echo $?`
