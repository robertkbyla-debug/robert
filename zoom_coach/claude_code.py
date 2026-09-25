"""Runs prompts through the Claude Code CLI (``claude -p``), so usage counts against a
Claude Pro/Max subscription instead of API credits.

Requires Claude Code installed and logged in with your Claude account (run ``claude`` once
and use ``/login``).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path


class ClaudeCodeError(RuntimeError):
    pass


def find_claude() -> str:
    path = shutil.which("claude")
    if not path:
        raise ClaudeCodeError(
            "Claude Code isn't installed or isn't on your PATH. Install it from "
            "https://claude.com/claude-code, run `claude` once and log in with your Claude account."
        )
    return path


class ClaudeCodeRunner:
    def __init__(self, *, model: str | None = None, timeout: float = 180.0) -> None:
        self.executable = find_claude()
        self.model = model
        self.timeout = timeout
        # A neutral working directory keeps project CLAUDE.md files and settings out of the prompt.
        self._workdir = Path(tempfile.mkdtemp(prefix="zoom-coach-"))
        self._system_files: dict[str, Path] = {}

    def _system_file(self, system: str) -> Path:
        # The project context can be far larger than a command line allows, so pass it as a file.
        path = self._system_files.get(system)
        if path is None:
            path = self._workdir / f"system-{len(self._system_files)}.txt"
            path.write_text(system, encoding="utf-8")
            self._system_files[system] = path
        return path

    async def run(self, *, system: str, prompt: str, schema: dict, effort: str) -> dict:
        args = [
            self.executable, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt-file", str(self._system_file(system)),
            "--tools", "",
            "--setting-sources", "",
            "--no-session-persistence",
            "--effort", effort,
        ]
        if self.model:
            args += ["--model", self.model]

        env = dict(os.environ)
        # An API key in the environment would take priority over the subscription login and
        # bill API credits, which is exactly what this backend exists to avoid.
        env.pop("ANTHROPIC_API_KEY", None)

        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=self._workdir,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(prompt.encode("utf-8")), self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeCodeError(f"Claude Code took longer than {self.timeout:.0f}s") from None

        try:
            result = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()[-500:]
            raise ClaudeCodeError(f"Claude Code failed (exit {proc.returncode}): {detail}") from None

        if result.get("is_error") or result.get("subtype") != "success":
            detail = result.get("result") or result.get("subtype") or "unknown error"
            raise ClaudeCodeError(f"Claude Code error: {detail}")
        output = result.get("structured_output")
        if not isinstance(output, dict):
            raise ClaudeCodeError("Claude Code returned no structured output.")
        return output
