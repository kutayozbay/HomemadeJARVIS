"""Speech-to-text with faster-whisper. Uses the GPU when it works, otherwise the CPU."""
from __future__ import annotations

import numpy as np


class Transcriber:
    def __init__(self, model: str = "small", language: str | None = "en"):
        from faster_whisper import WhisperModel

        self.language = language
        try:
            self._model = WhisperModel(model, device="cuda", compute_type="float16")
            # Decoding is lazy and CUDA problems (e.g. a missing cublas DLL) only appear on a real
            # decode, so force one on a second of silence, without the VAD filter that would skip it.
            segments, _ = self._model.transcribe(np.zeros(16000, dtype="float32"), vad_filter=False, beam_size=1)
            list(segments)
            self.device = "cuda"
        except Exception:
            self._model = WhisperModel(model, device="cpu", compute_type="int8")
            self.device = "cpu"

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self._model.transcribe(
            audio, language=self.language, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()
