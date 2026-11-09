"""PreToolUse hook: block `git commit` / `git push` unless lint, types and tests pass.

Claude Code sends the tool call as JSON on stdin; the shell command is at
`tool_input.command`. Exit code 2 blocks the call and feeds stderr back to
Claude so it fixes the problem before retrying. Exit 0 lets the call run.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GIT_WRITE = re.compile(r"\bgit\s+(commit|push)\b")


def venv_python() -> str:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # not our business; never block on malformed input
    command = str(payload.get("tool_input", {}).get("command", ""))
    if not GIT_WRITE.search(command):
        return 0

    py = venv_python()
    checks = [
        ("ruff (lint)", [py, "-m", "ruff", "check", "."]),
        ("mypy (types)", [py, "-m", "mypy"]),
        ("pytest (tests)", [py, "-m", "pytest", "-q"]),
    ]
    for name, cmd in checks:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()[-3000:]
            print(f"BLOCKED: {name} failed. Fix it before committing/pushing.\n\n{output}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
