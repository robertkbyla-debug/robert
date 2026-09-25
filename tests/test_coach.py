import asyncio
from types import SimpleNamespace

from zoom_coach.coach import COACH_INSTRUCTIONS, Coach, CoachError, CoachingUpdate


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def response(parsed, stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=1, cache_read_input_tokens=0, output_tokens=1)
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason, usage=usage)


def update():
    return CoachingUpdate(read="r", say_next="s", tips=[], goals=[], risks=[], open_questions=[], running_summary="sum")


def run_analyze(coach, **overrides):
    args = dict(title="Call", goals=["Book pilot"], notes=["note A"], transcript="[00:01] Dana: hi",
                truncated=False, previous=None, elapsed_min=3)
    args.update(overrides)
    return asyncio.run(coach.analyze(**args))


def test_request_shape():
    messages = FakeMessages(response(update()))
    coach = Coach("PROJECT FACTS", me="Robert", client=SimpleNamespace(messages=messages))
    run_analyze(coach, previous=update(), truncated=True)

    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5" and kw["output_format"] is CoachingUpdate
    assert kw["output_config"] == {"effort": "low"}
    assert kw["system"][0]["text"] == COACH_INSTRUCTIONS
    assert "PROJECT FACTS" in kw["system"][1]["text"] and kw["system"][1]["cache_control"]
    user = kw["messages"][0]["content"]
    for expected in ["Book pilot", "note A", "Dana: hi", "Robert", "<previous_update>", "<summary_of_earlier_call>"]:
        assert expected in user
    assert kw["extra_body"] == {"fallbacks": "default"}


def test_no_fallbacks_and_refusal():
    messages = FakeMessages(response(None, stop_reason="refusal"))
    coach = Coach("", use_fallbacks=False, client=SimpleNamespace(messages=messages))
    try:
        run_analyze(coach)
    except CoachError as exc:
        assert "declined" in str(exc)
    else:
        raise AssertionError("refusal should raise")
    assert "extra_body" not in messages.kwargs
