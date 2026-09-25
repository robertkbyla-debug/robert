"""Transcript storage and parsing of common transcript formats.

Supported input formats (mixed freely, one utterance per line or block):

* Zoom desktop "Save transcript" / saved captions::

      [Jane Doe] 14:03:22
      Thanks for making time today.

* WebVTT (Zoom cloud recordings, Teams, Meet exports)::

      00:00:01.000 --> 00:00:04.000
      Jane Doe: Thanks for making time today.

* Timestamped lines: ``14:03:22 Jane Doe: Thanks for making time today.``
* Plain ``Speaker: text`` lines, or plain text lines with no speaker.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass

_ZOOM_HEADER = re.compile(r"^\[(?P<speaker>[^\]]{1,80})\]\s*\d{1,2}:\d{2}(?::\d{2})?\s*$")
_VTT_TIMING = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}\s*-->\s*")
_TIMESTAMPED = re.compile(
    r"^\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s+(?P<speaker>[^:]{1,60}?):\s+(?P<text>.+)$"
)
_SPEAKER_LINE = re.compile(r"^(?P<speaker>[A-Z][\w .'\-]{0,58}?):\s+(?P<text>.+)$")
_VTT_TAG = re.compile(r"</?v[^>]*>")


@dataclass
class Segment:
    id: int
    ts: float
    speaker: str | None
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_transcript_text(raw: str) -> list[tuple[str | None, str]]:
    """Parse transcript text into ``(speaker, text)`` utterances."""
    utterances: list[tuple[str | None, str]] = []
    pending_speaker: str | None = None

    for line in raw.splitlines():
        line = line.strip().lstrip("﻿")
        if not line or line == "WEBVTT" or line.isdigit() or _VTT_TIMING.match(line):
            continue
        line = _VTT_TAG.sub("", line).strip()
        if not line:
            continue

        if m := _ZOOM_HEADER.match(line):
            pending_speaker = m["speaker"].strip()
            continue
        if m := _TIMESTAMPED.match(line):
            utterances.append((m["speaker"].strip(), m["text"].strip()))
            continue
        if m := _SPEAKER_LINE.match(line):
            utterances.append((m["speaker"].strip(), m["text"].strip()))
            continue
        utterances.append((pending_speaker, line))

    return utterances


class Transcript:
    """Append-only transcript of the call."""

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.started_at = time.time()
        self._next_id = 1

    def add(self, text: str, speaker: str | None = None, ts: float | None = None) -> Segment | None:
        text = " ".join(text.split())
        if not text:
            return None
        speaker = speaker.strip() if speaker and speaker.strip() else None
        segment = Segment(id=self._next_id, ts=ts or time.time(), speaker=speaker, text=text)
        self._next_id += 1
        self.segments.append(segment)
        return segment

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)

    def render(self, max_chars: int | None = None) -> tuple[str, bool]:
        """Render as ``[mm:ss] Speaker: text`` lines.

        Returns the text and whether older lines were dropped to fit ``max_chars``.
        """
        lines: list[str] = []
        total = 0
        truncated = False
        for segment in reversed(self.segments):
            line = self._format(segment)
            if max_chars is not None and total + len(line) + 1 > max_chars:
                truncated = True
                break
            lines.append(line)
            total += len(line) + 1
        lines.reverse()
        return "\n".join(lines), truncated

    def _format(self, segment: Segment) -> str:
        elapsed = max(0, int(segment.ts - self.started_at))
        stamp = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        who = segment.speaker or "Unknown"
        return f"[{stamp}] {who}: {segment.text}"
