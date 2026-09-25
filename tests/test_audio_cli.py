import pytest

from zoom_coach.__main__ import build_parser, build_sources
from zoom_coach.sources.audio import resolve_device


class FakeSD:
    def query_hostapis(self):
        return [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}]

    def query_devices(self):
        return [
            {"name": "Speakers (Realtek)", "max_input_channels": 0, "hostapi": 0},
            {"name": "CABLE Output (VB-Audio Virtual Cable)", "max_input_channels": 2, "hostapi": 2},
            {"name": "CABLE Output (VB-Audio Virtual ", "max_input_channels": 2, "hostapi": 0},
            {"name": "CABLE Output (VB-Audio Virtual Cable)", "max_input_channels": 2, "hostapi": 1},
            {"name": "Microphone (USB)", "max_input_channels": 1, "hostapi": 2},
        ]


def test_resolve_prefers_mme_among_duplicates():
    assert resolve_device(FakeSD(), "cable output") == 2
    assert resolve_device(FakeSD(), "Microphone") == 4
    assert resolve_device(FakeSD(), 7) == 7 and resolve_device(FakeSD(), None) is None


def test_resolve_unknown_or_output_only_device():
    with pytest.raises(RuntimeError, match="list-devices"):
        resolve_device(FakeSD(), "Speakers")


def test_mic_and_call_audio_sources_are_labelled():
    args = build_parser().parse_args(
        ["--source", "audio", "--mic", "default", "--call-audio", "CABLE Output", "--me", "Robert"]
    )
    mic, call = build_sources(args)
    assert (mic.device, mic.speaker_label) == (None, "Robert")
    assert (call.device, call.speaker_label) == ("CABLE Output", "Other side")


def test_single_device_fallback():
    (only,) = build_sources(build_parser().parse_args(["--source", "audio", "--device", "3"]))
    assert only.device == 3 and only.speaker_label is None
