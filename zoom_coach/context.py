"""Loads project context (notes, briefs, account history) from files and folders."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

CONTEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"}
MAX_CONTEXT_CHARS = 400_000


def load_context(paths: list[str]) -> str:
    """Concatenate every readable text file under ``paths`` into one context block."""
    files: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(
                p for p in sorted(path.rglob("*"))
                if p.is_file() and p.suffix.lower() in CONTEXT_SUFFIXES and not p.name.startswith(".")
            )
        elif path.is_file():
            files.append(path)
        else:
            log.warning("Context path not found: %s", path)

    parts: list[str] = []
    total = 0
    for file in files:
        try:
            text = file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            log.warning("Could not read %s: %s", file, exc)
            continue
        if not text:
            continue
        block = f'<document name="{file.name}">\n{text}\n</document>'
        if total + len(block) > MAX_CONTEXT_CHARS:
            log.warning("Context limit reached; skipping %s and later files", file)
            break
        parts.append(block)
        total += len(block)

    log.info("Loaded %d context file(s), %d chars", len(parts), total)
    return "\n\n".join(parts)
