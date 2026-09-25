import os
import time

from zoom_coach.sources.file_tail import FileTailSource


def collect():
    got = []
    return got, lambda text, speaker: got.append((speaker, text))


def test_follows_appends_and_waits_for_complete_lines(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Jane: hello\nBob: hi th")
    src = FileTailSource(str(f))
    got, emit = collect()

    assert src.poll(emit) == 1
    with f.open("a") as fh:
        fh.write("ere\nJane: great\n")
    assert src.poll(emit) == 2
    assert src.poll(emit) == 0
    assert got == [("Jane", "hello"), ("Bob", "hi there"), ("Jane", "great")]


def test_full_rewrites_only_emit_new_utterances(tmp_path):
    f = tmp_path / "captions.txt"
    f.write_text("[Jane] 10:00:00\nhello\n")
    src = FileTailSource(str(f))
    got, emit = collect()
    src.poll(emit)
    f.write_text("[Jane] 10:00:00\nhello\n[Bob] 10:00:05\nhi\n")
    src.poll(emit)
    assert got == [("Jane", "hello"), ("Bob", "hi")]


def test_skip_existing(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("A: old\n")
    src = FileTailSource(str(f), from_start=False)
    got, emit = collect()
    src.poll(emit)
    with f.open("a") as fh:
        fh.write("A: new\n")
    src.poll(emit)
    assert got == [("A", "new")]


def test_glob_switches_to_newest_file(tmp_path):
    old = tmp_path / "m1" / "captions.txt"
    old.parent.mkdir()
    old.write_text("A: first meeting\n")
    src = FileTailSource(str(tmp_path / "*" / "captions.txt"))
    got, emit = collect()
    src.poll(emit)

    new = tmp_path / "m2" / "captions.txt"
    new.parent.mkdir()
    new.write_text("B: second meeting\n")
    later = time.time() + 5
    os.utime(new, (later, later))
    src.poll(emit)
    assert got == [("A", "first meeting"), ("B", "second meeting")]
