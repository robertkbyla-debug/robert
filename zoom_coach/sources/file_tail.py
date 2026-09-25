"""Follows a transcript file that another program keeps writing.

Works both for files that are appended to and for files that are rewritten in full on every
save (as Zoom does with saved captions): each poll re-parses the file and emits only the
utterances beyond those already seen. A glob pattern follows the newest matching file.
"""

from __future__ import annotations

import asyncio
import glob
import logging
from pathlib import Path

from ..transcript import parse_transcript_text
from . import Emit

log = logging.getLogger(__name__)


class FileTailSource:
    def __init__(self, pattern: str, *, poll_seconds: float = 1.0, from_start: bool = True) -> None:
        self.pattern = str(Path(pattern).expanduser())
        self.poll_seconds = poll_seconds
        self.from_start = from_start
        self._path: str | None = None
        self._seen = 0
        self._last_content: str | None = None

    def _resolve(self) -> str | None:
        if glob.has_magic(self.pattern):
            matches = [p for p in glob.glob(self.pattern) if Path(p).is_file()]
            return max(matches, key=lambda p: Path(p).stat().st_mtime) if matches else None
        return self.pattern if Path(self.pattern).is_file() else None

    def poll(self, emit: Emit) -> int:
        """Read the file once and emit new utterances. Returns how many were emitted."""
        path = self._resolve()
        if path is None:
            return 0
        skip_existing = False
        if path != self._path:
            skip_existing = self._path is None and not self.from_start
            log.info("Following transcript file %s", path)
            self._path, self._seen, self._last_content = path, 0, None

        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.warning("Could not read %s: %s", path, exc)
            return 0
        if content == self._last_content:
            return 0
        self._last_content = content

        utterances = parse_transcript_text(self._complete_part(content))
        if skip_existing or len(utterances) < self._seen:
            # Starting mid-file, or the file was truncated/replaced: treat what is there as seen.
            self._seen = len(utterances)
            return 0
        new = utterances[self._seen:]
        for speaker, text in new:
            emit(text, speaker)
        self._seen = len(utterances)
        return len(new)

    @staticmethod
    def _complete_part(content: str) -> str:
        # Ignore a trailing line that is still being written.
        if content.endswith("\n"):
            return content
        cut = content.rfind("\n")
        return content[: cut + 1] if cut >= 0 else ""

    async def run(self, emit: Emit) -> None:
        log.info("Watching %s for transcript updates", self.pattern)
        while True:
            self.poll(emit)
            await asyncio.sleep(self.poll_seconds)
