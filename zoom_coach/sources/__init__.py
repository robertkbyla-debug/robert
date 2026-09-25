"""Transcript sources. Each source calls ``emit(text, speaker)`` for every new utterance."""

from collections.abc import Callable

Emit = Callable[[str, "str | None"], None]
