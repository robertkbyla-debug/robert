"""Transcribes audio input devices locally with faster-whisper.

To hear the other side of a Zoom call, capture the call's audio through a virtual/loopback
device (VB-Audio Cable or "Stereo Mix" on Windows, BlackHole on macOS, a PulseAudio/PipeWire
monitor source on Linux). Listening to your microphone and the call audio as two separate
sources labels who said what.

Requires the optional extras: ``pip install -e ".[audio]"``.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading

from . import Emit

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000

_model = None
_model_lock = threading.Lock()


def _import_audio():
    try:
        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise SystemExit(
            "Audio capture needs extra packages. Install them with:  pip install -e \".[audio]\""
        ) from exc
    return np, sd, WhisperModel


def list_devices() -> str:
    _, sd, _ = _import_audio()
    return str(sd.query_devices())


def resolve_device(sd, device: str | int | None):
    """Find an input device by index or (partial, case-insensitive) name.

    Windows lists each device once per host API (MME, DirectSound, WASAPI...), which makes a
    plain name ambiguous. Prefer MME, which accepts any sample rate and resamples for us.
    """
    if device is None or isinstance(device, int):
        return device
    hostapis = [h["name"] for h in sd.query_hostapis()]
    matches = [
        (i, d) for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0 and device.lower() in d["name"].lower()
    ]
    if not matches:
        raise RuntimeError(f"No input device matches {device!r}. Run `zoom-coach --list-devices` to see them.")
    preferred = ["MME", "Windows DirectSound", "Core Audio", "ALSA", "JACK Audio Connection Kit"]
    matches.sort(key=lambda m: preferred.index(hostapis[m[1]["hostapi"]])
                 if hostapis[m[1]["hostapi"]] in preferred else len(preferred))
    return matches[0][0]


def _shared_model(WhisperModel, size: str, device: str):
    # One model serves every audio source, so listening to two devices doesn't double memory use.
    global _model
    with _model_lock:
        if _model is None:
            log.info("Loading Whisper model %s on %s (the first run downloads it)...", size, device)
            _model = WhisperModel(size, device=device, compute_type="int8")
    return _model


class AudioSource:
    def __init__(
        self,
        *,
        device: str | None = None,
        model_size: str = "small.en",
        whisper_device: str = "cpu",
        chunk_seconds: float = 6.0,
        speaker_label: str | None = None,
        language: str | None = "en",
    ) -> None:
        self.device = int(device) if device and device.isdigit() else device
        self.model_size = model_size
        self.whisper_device = whisper_device
        self.chunk_seconds = chunk_seconds
        self.speaker_label = speaker_label
        self.language = language

    async def run(self, emit: Emit) -> None:
        loop = asyncio.get_running_loop()
        errors: list[BaseException] = []

        def emit_threadsafe(text: str) -> None:
            loop.call_soon_threadsafe(emit, text, self.speaker_label)

        def target() -> None:
            try:
                self._capture(emit_threadsafe, stop)
            except BaseException as exc:  # surfaced to the UI through the source runner
                errors.append(exc)

        stop = threading.Event()
        worker = threading.Thread(target=target, daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                await asyncio.sleep(0.5)
        finally:
            stop.set()
        if errors:
            raise RuntimeError(f"Audio device {self.device!r}: {errors[0]}") from errors[0]

    def _capture(self, emit_text, stop: threading.Event) -> None:
        np, sd, WhisperModel = _import_audio()
        model = _shared_model(WhisperModel, self.model_size, self.whisper_device)
        blocks: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("audio status: %s", status)
            blocks.put(indata.copy())

        device = resolve_device(sd, self.device)
        chunk_samples = int(self.chunk_seconds * SAMPLE_RATE)
        buffer = np.zeros(0, dtype=np.float32)
        with sd.InputStream(
            device=device, channels=1, samplerate=SAMPLE_RATE, dtype="float32", callback=callback
        ):
            name = self.device if self.device is not None else "(default microphone)"
            log.info("Listening on %s%s", name, f" as {self.speaker_label}" if self.speaker_label else "")
            while not stop.is_set():
                try:
                    block = blocks.get(timeout=0.5)
                except queue.Empty:
                    continue
                buffer = np.concatenate([buffer, block[:, 0]])
                if len(buffer) < chunk_samples:
                    continue
                chunk, buffer = buffer, np.zeros(0, dtype=np.float32)
                with _model_lock:
                    segments, _ = model.transcribe(
                        chunk, language=self.language, vad_filter=True, condition_on_previous_text=False
                    )
                    text = " ".join(s.text.strip() for s in segments).strip()
                if text:
                    emit_text(text)
