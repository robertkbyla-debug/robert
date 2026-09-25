"""Web server: holds the live session, runs the coaching loop and streams updates to the UI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .coach import CoachingUpdate, Debrief
from .transcript import Transcript, parse_transcript_text

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@dataclass
class Settings:
    title: str = "Live call"
    goals: list[str] = field(default_factory=list)
    interval_seconds: float = 20.0
    min_new_chars: int = 200
    max_transcript_chars: int = 150_000
    sessions_dir: Path = Path("sessions")


class Session:
    """Everything known about the call in progress, plus the coaching loop."""

    def __init__(self, coach: Any, settings: Settings) -> None:
        self.coach = coach
        self.settings = settings
        self.title = settings.title
        self.goals = list(settings.goals)
        self.notes: list[str] = []
        self.transcript = Transcript()
        self.update: CoachingUpdate | None = None
        self.update_at: float | None = None
        self.debrief: Debrief | None = None
        self.paused = False
        self.status = "waiting"
        self.error: str | None = None

        self._analyzed_chars = 0
        self._analyzed_at = time.time()
        self._force = False
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()

    # -- events -----------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: str, data: Any) -> None:
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait((event, data))

    def snapshot(self) -> dict:
        return {
            "title": self.title,
            "goals": self.goals,
            "notes": self.notes,
            "paused": self.paused,
            "status": self.status,
            "error": self.error,
            "started_at": self.transcript.started_at,
            "segments": [s.to_dict() for s in self.transcript.segments[-300:]],
            "update": self.update.model_dump() if self.update else None,
            "update_at": self.update_at,
            "debrief": self.debrief.model_dump() if self.debrief else None,
        }

    def _set_status(self, status: str, error: str | None = None) -> None:
        self.status, self.error = status, error
        self.publish("status", {"status": status, "error": error, "paused": self.paused})

    # -- inputs -----------------------------------------------------------------

    def add_utterance(self, text: str, speaker: str | None = None) -> None:
        segment = self.transcript.add(text, speaker)
        if segment:
            self.publish("segment", segment.to_dict())
            if self.status == "waiting":
                self._set_status("listening")
            self._wake.set()

    def add_raw_transcript(self, raw: str) -> int:
        utterances = parse_transcript_text(raw)
        for speaker, text in utterances:
            self.add_utterance(text, speaker)
        return len(utterances)

    def add_note(self, note: str) -> None:
        self.notes.append(note.strip())
        self.publish("notes", self.notes)
        self.request_analysis()

    def set_goals(self, goals: list[str]) -> None:
        self.goals = [g.strip() for g in goals if g.strip()]
        self.publish("goals", self.goals)
        self.request_analysis()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self._set_status(self.status, self.error)
        if not paused:
            self._wake.set()

    def request_analysis(self) -> None:
        self._force = True
        self._wake.set()

    # -- coaching ---------------------------------------------------------------

    def _due(self) -> bool:
        if self._force:
            return True
        if self.paused:
            return False
        new_chars = self.transcript.char_count - self._analyzed_chars
        if new_chars <= 0:
            return False
        since = time.time() - self._analyzed_at
        if since < self.settings.interval_seconds:
            return False
        # Enough new talk, or a little new talk that has sat unanalysed for a while.
        return new_chars >= self.settings.min_new_chars or since >= self.settings.interval_seconds * 3

    async def run_coaching_loop(self) -> None:
        while True:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=2.0)
            self._wake.clear()
            if self._due():
                await self.analyze()

    async def analyze(self) -> None:
        async with self._lock:
            self._force = False
            chars = self.transcript.char_count
            transcript, truncated = self.transcript.render(self.settings.max_transcript_chars)
            self._set_status("analyzing")
            started = time.time()
            try:
                update = await self.coach.analyze(
                    title=self.title,
                    goals=self.goals,
                    notes=self.notes,
                    transcript=transcript,
                    truncated=truncated,
                    previous=self.update,
                    elapsed_min=(time.time() - self.transcript.started_at) / 60,
                )
            except Exception as exc:  # keep coaching alive through transient API errors
                log.exception("Coaching request failed")
                self._analyzed_at = time.time()
                self._set_status("error", f"{type(exc).__name__}: {exc}")
                return
            self.update, self.update_at = update, time.time()
            self._analyzed_chars, self._analyzed_at = chars, self.update_at
            log.info("Coaching update in %.1fs", self.update_at - started)
            self.publish("update", {"update": update.model_dump(), "update_at": self.update_at})
            self._set_status("listening")

    async def run_debrief(self) -> Debrief:
        async with self._lock:
            transcript, truncated = self.transcript.render(self.settings.max_transcript_chars)
            self._set_status("debriefing")
            try:
                debrief = await self.coach.debrief(
                    title=self.title,
                    goals=self.goals,
                    notes=self.notes,
                    transcript=transcript,
                    truncated=truncated,
                    summary=self.update.running_summary if self.update else None,
                    elapsed_min=(time.time() - self.transcript.started_at) / 60,
                )
            except Exception as exc:
                log.exception("Debrief request failed")
                self._set_status("error", f"{type(exc).__name__}: {exc}")
                raise
            self.debrief = debrief
            self.publish("debrief", debrief.model_dump())
            self._set_status("listening")
        self.save()
        return debrief

    # -- persistence ------------------------------------------------------------

    def save(self) -> Path | None:
        if not self.transcript.segments and not self.notes:
            return None
        directory = self.settings.sessions_dir
        directory.mkdir(parents=True, exist_ok=True)
        start = datetime.fromtimestamp(self.transcript.started_at)
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")[:40] or "call"
        base = directory / f"{start:%Y%m%d-%H%M}-{slug}"
        base.with_suffix(".json").write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        base.with_suffix(".md").write_text(self._markdown(), encoding="utf-8")
        log.info("Saved session to %s.{md,json}", base)
        return base

    def _markdown(self) -> str:
        start = datetime.fromtimestamp(self.transcript.started_at)
        out = [f"# {self.title}", f"_{start:%Y-%m-%d %H:%M}_", ""]
        if self.goals:
            out += ["## Goals", *[f"- {g}" for g in self.goals], ""]
        if self.debrief:
            d = self.debrief
            out += ["## Debrief", d.summary, "", f"**Outcome:** {d.outcome}", ""]
            if d.decisions:
                out += ["### Decisions", *[f"- {x}" for x in d.decisions], ""]
            if d.action_items:
                out += ["### Action items"]
                out += [f"- [ ] **{a.owner}**: {a.item}" + (f" ({a.due})" if a.due else "") for a in d.action_items]
                out.append("")
            if d.missed_opportunities:
                out += ["### Missed opportunities", *[f"- {x}" for x in d.missed_opportunities], ""]
            out += ["### Follow-up email", "```", d.follow_up_email, "```", ""]
        elif self.update:
            out += ["## Summary so far", self.update.running_summary, ""]
        if self.notes:
            out += ["## Your notes", *[f"- {n}" for n in self.notes], ""]
        transcript, _ = self.transcript.render()
        out += ["## Transcript", "```", transcript, "```", ""]
        return "\n".join(out)


class UtteranceIn(BaseModel):
    text: str
    speaker: str | None = None
    raw: bool = False


class NoteIn(BaseModel):
    text: str


class GoalsIn(BaseModel):
    goals: list[str]
    title: str | None = None


class PauseIn(BaseModel):
    paused: bool


def create_app(session: Session, sources: list | None = None) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = [asyncio.create_task(session.run_coaching_loop())]
        for source in sources or []:
            tasks.append(asyncio.create_task(_run_source(source, session)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            session.save()

    app = FastAPI(title="Zoom Coach", lifespan=lifespan)
    app.state.session = session

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def state():
        return session.snapshot()

    @app.get("/api/events")
    async def events(request: Request):
        queue = session.subscribe()

        async def stream():
            try:
                yield _sse("snapshot", session.snapshot())
                while True:
                    try:
                        event, data = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": keep-alive\n\n"
                        continue
                    yield _sse(event, data)
            finally:
                session.unsubscribe(queue)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/api/transcript")
    async def add_transcript(body: UtteranceIn):
        if body.raw:
            return {"added": session.add_raw_transcript(body.text)}
        session.add_utterance(body.text, body.speaker)
        return {"added": 1}

    @app.post("/api/notes")
    async def add_note(body: NoteIn):
        if not body.text.strip():
            raise HTTPException(400, "Note is empty")
        session.add_note(body.text)
        return {"notes": session.notes}

    @app.put("/api/goals")
    async def set_goals(body: GoalsIn):
        if body.title and body.title.strip():
            session.title = body.title.strip()
        session.set_goals(body.goals)
        return {"goals": session.goals, "title": session.title}

    @app.post("/api/analyze")
    async def analyze():
        session.request_analysis()
        return {"ok": True}

    @app.post("/api/pause")
    async def pause(body: PauseIn):
        session.set_paused(body.paused)
        return {"paused": session.paused}

    @app.post("/api/debrief")
    async def debrief():
        try:
            result = await session.run_debrief()
        except Exception as exc:
            raise HTTPException(502, f"Debrief failed: {exc}") from exc
        return result.model_dump()

    return app


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _run_source(source, session: Session) -> None:
    try:
        await source.run(session.add_utterance)
    except asyncio.CancelledError:
        raise
    except (Exception, SystemExit) as exc:
        log.exception("Transcript source stopped")
        session._set_status("error", f"Transcript source stopped: {exc}")
