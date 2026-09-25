import asyncio
import json

from fastapi.testclient import TestClient

from zoom_coach.coach import ActionItem, CoachingUpdate, Debrief, GoalStatus, Tip
from zoom_coach.server import Session, Settings, create_app


class FakeCoach:
    def __init__(self):
        self.calls = []

    async def analyze(self, **kwargs):
        self.calls.append(kwargs)
        return CoachingUpdate(
            read="Early rapport, price concern surfacing.",
            say_next="What would Sam need to see to say yes to a pilot?",
            tips=[Tip(kind="ask", text="Ask who signs off", why="Budget owner unknown", priority="high")],
            goals=[GoalStatus(goal=g, status="in_progress", evidence="discussed") for g in kwargs["goals"]],
            risks=["Price vs DispatchPro"],
            open_questions=["Training plan"],
            running_summary="Dana likes the app; price and training are concerns.",
        )

    async def debrief(self, **kwargs):
        return Debrief(
            summary="Good call.",
            outcome="Pilot interest, no date yet.",
            decisions=["Share ROI numbers"],
            action_items=[ActionItem(owner="Robert", item="Send ROI sheet", due="Friday")],
            goals=[],
            missed_opportunities=["Did not book Sam"],
            follow_up_email="Hi Dana, ...",
        )


def make(tmp_path, **settings):
    coach = FakeCoach()
    session = Session(coach, Settings(title="Demo call", goals=["Book a pilot"], sessions_dir=tmp_path, **settings))
    return coach, session


def test_due_logic(tmp_path):
    _, session = make(tmp_path, interval_seconds=10, min_new_chars=20)
    assert not session._due()
    session.add_utterance("this is a much longer sentence of new talk", "B")
    assert not session._due()  # interval has not passed yet
    session._analyzed_at -= 11
    assert session._due()
    session._analyzed_chars = session.transcript.char_count
    session.add_utterance("short", "A")
    assert not session._due()  # too little new text
    session._analyzed_at -= 20
    assert session._due()  # a little new text that has waited 3 intervals
    session.set_paused(True)
    assert not session._due()
    session.request_analysis()
    assert session._due()  # explicit requests run even when paused


def test_analyze_passes_context_and_previous_update(tmp_path):
    coach, session = make(tmp_path)
    session.add_utterance("Price is going to come up.", "Dana")
    session.add_note("Push for a pilot start date")
    asyncio.run(session.analyze())
    asyncio.run(session.analyze())

    first, second = coach.calls
    assert "Dana: Price is going to come up." in first["transcript"]
    assert first["goals"] == ["Book a pilot"] and first["notes"] == ["Push for a pilot start date"]
    assert first["previous"] is None and second["previous"] is not None
    assert session.status == "listening" and session._analyzed_chars == session.transcript.char_count


def test_analyze_error_is_reported_not_raised(tmp_path):
    coach, session = make(tmp_path)

    async def boom(**kwargs):
        raise RuntimeError("rate limited")

    coach.analyze = boom
    asyncio.run(session.analyze())
    assert session.status == "error" and "rate limited" in session.error


def test_api_flow_and_session_saved(tmp_path):
    _, session = make(tmp_path)
    with TestClient(create_app(session)) as client:
        assert client.get("/").status_code == 200
        r = client.post("/api/transcript", json={"text": "[Dana] 10:00:00\nHello\nBob: hi\n", "raw": True})
        assert r.json() == {"added": 2}
        client.post("/api/transcript", json={"text": "One more line", "speaker": "Dana"})
        client.post("/api/notes", json={"text": "They want SSO"})
        r = client.put("/api/goals", json={"goals": ["Book a pilot", " ", "Meet Sam"], "title": "Northwind"})
        assert r.json() == {"goals": ["Book a pilot", "Meet Sam"], "title": "Northwind"}
        assert client.post("/api/notes", json={"text": "  "}).status_code == 400

        state = client.get("/api/state").json()
        assert [s["speaker"] for s in state["segments"]] == ["Dana", "Bob", "Dana"]

        r = client.post("/api/debrief")
        assert r.status_code == 200 and r.json()["outcome"] == "Pilot interest, no date yet."

    saved = list(tmp_path.glob("*-northwind.md"))
    assert saved, "session markdown should be saved"
    text = saved[0].read_text()
    assert "Send ROI sheet" in text and "Dana: One more line" in text
    data = json.loads(saved[0].with_suffix(".json").read_text())
    assert data["debrief"]["summary"] == "Good call."
