"""Transcribes an audio input device locally with faster-whisper.

To hear both sides of a Zoom call, capture system audio through a loopback device
(BlackHole on macOS, "Stereo Mix" or VB-Cable on Windows, a PulseAudio/PipeWire monitor
source on Linux) or a multi-output device that combines it with your microphone.

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


class AudioSource:
    def __init__(
        self,
        *,
        device: str | None = None,
        model_size: str = "small.en",
        chunk_seconds: float = 6.0,
        speaker_label: str | None = None,
        language: str | None = "en",
    ) -> None:
        self.device = int(device) if device and device.isdigit() else device
        self.model_size = model_size
        self.chunk_seconds = chunk_seconds
        self.speaker_label = speaker_label
        self.language = language

    async def run(self, emit: Emit) -> None:
        loop = asyncio.get_running_loop()

        def emit_threadsafe(text: str) -> None:
            loop.call_soon_threadsafe(emit, text, self.speaker_label)

        stop = threading.Event()
        worker = threading.Thread(target=self._capture, args=(emit_threadsafe, stop), daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                await asyncio.sleep(0.5)
        finally:
            stop.set()

    def _capture(self, emit_text, stop: threading.Event) -> None:
        np, sd, WhisperModel = _import_audio()
        log.info("Loading Whisper model %s (first run downloads it)...", self.model_size)
        model = WhisperModel(self.model_size, device="auto", compute_type="int8")
        blocks: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("audio status: %s", status)
            blocks.put(indata.copy())

        chunk_samples = int(self.chunk_seconds * SAMPLE_RATE)
        buffer = np.zeros(0, dtype=np.float32)
        with sd.InputStream(
            device=self.device, channels=1, samplerate=SAMPLE_RATE, dtype="float32", callback=callback
        ):
            log.info("Listening on audio device %s", self.device if self.device is not None else "(default)")
            while not stop.is_set():
                try:
                    block = blocks.get(timeout=0.5)
                except queue.Empty:
                    continue
                buffer = np.concatenate([buffer, block[:, 0]])
                if len(buffer) < chunk_samples:
                    continue
                chunk, buffer = buffer, np.zeros(0, dtype=np.float32)
                segments, _ = model.transcribe(
                    chunk, language=self.language, vad_filter=True, condition_on_previous_text=False
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                if text:
                    emit_text(text)
