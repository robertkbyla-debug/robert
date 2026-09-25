import asyncio
import json
import stat

from zoom_coach import claude_code
from zoom_coach.claude_code import ClaudeCodeError, ClaudeCodeRunner


def fake_cli(tmp_path, monkeypatch, body):
    """Install a stand-in `claude` script that records its args, stdin and env."""
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"log = {str(tmp_path / 'log.json')!r}\n"
        "json.dump({'args': sys.argv[1:], 'stdin': sys.stdin.read(),"
        " 'has_key': 'ANTHROPIC_API_KEY' in os.environ}, open(log, 'w'))\n"
        f"print({body!r})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: str(script))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-used")
    return tmp_path / "log.json"


def test_runner_invocation(tmp_path, monkeypatch):
    body = json.dumps({"is_error": False, "subtype": "success", "structured_output": {"ok": True}})
    log = fake_cli(tmp_path, monkeypatch, body)
    runner = ClaudeCodeRunner(model="opus")
    out = asyncio.run(runner.run(system="SYS", prompt="PROMPT", schema={"type": "object"}, effort="low"))

    assert out == {"ok": True}
    call = json.loads(log.read_text())
    args = call["args"]
    assert call["stdin"] == "PROMPT" and call["has_key"] is False
    assert args[args.index("--model") + 1] == "opus" and args[args.index("--effort") + 1] == "low"
    assert args[args.index("--tools") + 1] == ""
    system_file = args[args.index("--system-prompt-file") + 1]
    assert open(system_file).read() == "SYS"


def test_runner_reports_errors(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, json.dumps({"is_error": True, "subtype": "success", "result": "Not logged in"}))
    try:
        asyncio.run(ClaudeCodeRunner().run(system="s", prompt="p", schema={}, effort="low"))
    except ClaudeCodeError as exc:
        assert "Not logged in" in str(exc)
    else:
        raise AssertionError("expected ClaudeCodeError")


def test_missing_cli(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    try:
        ClaudeCodeRunner()
    except ClaudeCodeError as exc:
        assert "isn't installed" in str(exc)
    else:
        raise AssertionError("expected ClaudeCodeError")
