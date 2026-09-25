from zoom_coach.transcript import Transcript, parse_transcript_text


def test_zoom_saved_captions():
    raw = "[Jane Doe] 14:03:22\nThanks for joining.\n[Bob] 14:03:30\nHappy to.\nLet's start.\n"
    assert parse_transcript_text(raw) == [
        ("Jane Doe", "Thanks for joining."),
        ("Bob", "Happy to."),
        ("Bob", "Let's start."),
    ]


def test_vtt():
    raw = (
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\nJane Doe: Hello there\n\n"
        "2\n00:00:05.000 --> 00:00:07.500\n<v Bob>How are you?</v>\n"
    )
    assert parse_transcript_text(raw) == [("Jane Doe", "Hello there"), (None, "How are you?")]


def test_timestamped_and_plain_lines():
    raw = "10:01:02 Jane: We need this by March.\n[10:01:09] Bob: Noted.\nsome untagged words\n"
    assert parse_transcript_text(raw) == [
        ("Jane", "We need this by March."),
        ("Bob", "Noted."),
        (None, "some untagged words"),
    ]


def test_render_truncates_oldest_first():
    t = Transcript()
    t.started_at = 1000.0
    for i in range(10):
        t.add(f"line number {i}", "A", ts=1000.0 + i * 61)
    full, truncated = t.render()
    assert not truncated and full.splitlines()[0] == "[00:00] A: line number 0"
    assert full.splitlines()[-1] == "[09:09] A: line number 9"
    short, truncated = t.render(max_chars=60)
    assert truncated and short.endswith("line number 9") and "line number 0" not in short


def test_add_ignores_blank_text():
    t = Transcript()
    assert t.add("   ") is None
    assert t.add(" hello   world ", " ").text == "hello world"
    assert t.segments[0].speaker is None
