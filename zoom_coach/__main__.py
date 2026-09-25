"""Command line entry point: ``zoom-coach`` or ``python -m zoom_coach``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

from .coach import DEFAULT_MODEL, Coach
from .context import load_context
from .server import Session, Settings, create_app

EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zoom-coach",
        description="Live coaching for your calls: follows the transcript and suggests how to steer it.",
    )
    src = p.add_argument_group("transcript source")
    src.add_argument(
        "--source",
        choices=["none", "file", "audio", "replay"],
        default="none",
        help="none: paste or POST transcript lines yourself; file: follow a transcript file; "
        "audio: transcribe an audio device locally; replay: play back a saved transcript (demo)",
    )
    src.add_argument("--file", help="Transcript file (or glob, newest match is followed) for --source file/replay")
    src.add_argument("--skip-existing", action="store_true", help="With --source file, ignore what is already in the file")
    src.add_argument("--replay-speed", type=float, default=1.0, help="Replay speed multiplier (default 1.0)")
    src.add_argument("--device", help="Audio input device name or index for --source audio")
    src.add_argument("--whisper-model", default="small.en", help="faster-whisper model size (default small.en)")
    src.add_argument("--audio-speaker", help="Speaker label for transcribed audio (default: none)")
    src.add_argument("--list-devices", action="store_true", help="List audio devices and exit")

    call = p.add_argument_group("call")
    call.add_argument("--title", default="Live call", help="Name of the call")
    call.add_argument("--goal", action="append", default=[], help="A goal for the call (repeatable)")
    call.add_argument("--context", action="append", default=[], help="Project context file or folder (repeatable)")
    call.add_argument("--me", help="Your name as it appears in the transcript")

    coach = p.add_argument_group("coaching")
    coach.add_argument(
        "--backend",
        choices=["api", "claude-code"],
        default=os.environ.get("ZOOM_COACH_BACKEND", "api"),
        help="api: Anthropic API (uses API credits); claude-code: the `claude` CLI on your Claude Pro/Max plan",
    )
    coach.add_argument(
        "--model",
        default=os.environ.get("ZOOM_COACH_MODEL"),
        help=f"Claude model (api default {DEFAULT_MODEL}; claude-code default: your account's default, "
        "or an alias like opus / sonnet)",
    )
    coach.add_argument("--effort", choices=EFFORTS, default="low", help="Live-tip effort; low keeps tips fast (default low)")
    coach.add_argument("--debrief-effort", choices=EFFORTS, default="high")
    coach.add_argument("--interval", type=float, default=20.0, help="Minimum seconds between automatic updates (default 20)")
    coach.add_argument("--min-new-chars", type=int, default=200, help="New transcript characters needed to trigger an update")
    coach.add_argument("--no-fallbacks", action="store_true", help="Disable server-side model fallback on refusals")

    srv = p.add_argument_group("server")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--open", action="store_true", help="Open the coach panel in your browser")
    srv.add_argument("--sessions-dir", default="sessions", help="Where call notes are saved (default ./sessions)")
    srv.add_argument("-v", "--verbose", action="store_true")
    return p


def build_sources(args: argparse.Namespace) -> list:
    if args.source == "file":
        if not args.file:
            sys.exit("--source file needs --file PATH")
        from .sources.file_tail import FileTailSource

        return [FileTailSource(args.file, from_start=not args.skip_existing)]
    if args.source == "replay":
        if not args.file or not Path(args.file).is_file():
            sys.exit("--source replay needs --file pointing at a transcript")
        from .sources.replay import ReplaySource

        return [ReplaySource(args.file, speed=args.replay_speed)]
    if args.source == "audio":
        from .sources.audio import AudioSource

        return [AudioSource(device=args.device, model_size=args.whisper_model, speaker_label=args.audio_speaker)]
    return []


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_devices:
        from .sources.audio import list_devices

        print(list_devices())
        return

    import uvicorn

    from .claude_code import ClaudeCodeError

    try:
        coach = Coach(
            load_context(args.context),
            me=args.me,
            backend=args.backend,
            model=args.model,
            effort=args.effort,
            debrief_effort=args.debrief_effort,
            use_fallbacks=not args.no_fallbacks,
        )
    except ClaudeCodeError as exc:
        sys.exit(str(exc))
    settings = Settings(
        title=args.title,
        goals=args.goal,
        interval_seconds=args.interval,
        min_new_chars=args.min_new_chars,
        sessions_dir=Path(args.sessions_dir),
    )
    app = create_app(Session(coach, settings), build_sources(args))

    url = f"http://{args.host}:{args.port}"
    print(f"\n  Zoom Coach is running: {url}\n  Keep it open beside your call. Ctrl+C to stop (notes are saved).\n")
    if args.open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
