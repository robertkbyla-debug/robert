"""Replays a saved transcript at speaking pace, for demos and for rehearsing a call."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..transcript import parse_transcript_text
from . import Emit

log = logging.getLogger(__name__)

WORDS_PER_SECOND = 2.5


class ReplaySource:
    def __init__(self, path: str, *, speed: float = 1.0) -> None:
        self.path = Path(path).expanduser()
        self.speed = max(speed, 0.01)

    async def run(self, emit: Emit) -> None:
        utterances = parse_transcript_text(self.path.read_text(encoding="utf-8", errors="replace"))
        log.info("Replaying %d utterances from %s at %.1fx", len(utterances), self.path, self.speed)
        for speaker, text in utterances:
            await asyncio.sleep(len(text.split()) / WORDS_PER_SECOND / self.speed)
            emit(text, speaker)
        log.info("Replay finished")
