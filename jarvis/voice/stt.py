"""Speech-to-text with faster-whisper. Uses the GPU when it works, otherwise the CPU.

Whisper is multilingual. Letting it guess the language of a short sentence is unreliable, so the
guess is restricted to the languages you configured (default English and Turkish).
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def pick_language(probabilities: Sequence[tuple[str, float]], allowed: Sequence[str]) -> str:
    """The most likely language among the allowed ones (the first allowed one if none is scored)."""
    table = dict(probabilities)
    return max(allowed, key=lambda lang: table.get(lang, 0.0))


class Transcriber:
    def __init__(self, model: str = "small", languages: Sequence[str] = ("en", "tr")):
        from faster_whisper import WhisperModel

        self.languages = tuple(languages) or ("en",)
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

    def transcribe(self, audio: np.ndarray) -> tuple[str, str]:
        """Return (text, language code)."""
        language = self.languages[0]
        if len(self.languages) > 1:
            _, _, probabilities = self._model.detect_language(audio, vad_filter=False)
            language = pick_language(probabilities, self.languages)
        segments, _ = self._model.transcribe(
            audio, language=language, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip(), language
