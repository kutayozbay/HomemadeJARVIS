"""Speech-to-text with faster-whisper. Uses the GPU when it works, otherwise the CPU.

Three Whisper sizes, each for what it is good at (measured on this laptop's CPU, 4 s of speech):
  tiny   0.2 s  language detection (restricted to the configured languages, so it is reliable)
  base   0.4 s  the main language (English): fast and accurate enough
  small  1.3 s  every other language (e.g. Turkish), where the smaller models lose a lot of accuracy
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

DETECT_MODEL = "tiny"


def pick_language(probabilities: Sequence[tuple[str, float]], allowed: Sequence[str]) -> str:
    """The most likely language among the allowed ones (the first allowed one if none is scored)."""
    table = dict(probabilities)
    return max(allowed, key=lambda lang: table.get(lang, 0.0))


def uses_fast_model(language: str, languages: Sequence[str]) -> bool:
    """The fast model is for the main (first) language only."""
    return language == languages[0]


class Transcriber:
    def __init__(self, accurate_model: str = "small", languages: Sequence[str] = ("en", "tr"),
                 fast_model: str = "base"):
        from faster_whisper import WhisperModel

        self._cls = WhisperModel
        self.languages = tuple(languages) or ("en",)
        self.device, self._compute = "cpu", "int8"
        try:
            probe = WhisperModel(fast_model, device="cuda", compute_type="float16")
            # Decoding is lazy and CUDA problems (e.g. a missing cublas DLL) only appear on a real
            # decode, so force one on a second of silence, without the VAD filter that would skip it.
            segments, _ = probe.transcribe(np.zeros(16000, dtype="float32"), vad_filter=False, beam_size=1)
            list(segments)
            self.device, self._compute = "cuda", "float16"
        except Exception:
            pass
        self._fast = self._load(fast_model)
        self._accurate = self._fast if accurate_model == fast_model else (
            self._load(accurate_model) if len(self.languages) > 1 else self._fast)
        self._detector = self._load(DETECT_MODEL) if len(self.languages) > 1 else None

    def _load(self, name: str):
        return self._cls(name, device=self.device, compute_type=self._compute)

    def transcribe(self, audio: np.ndarray) -> tuple[str, str]:
        """Return (text, language code)."""
        language = self.languages[0]
        if self._detector is not None:
            _, _, probabilities = self._detector.detect_language(audio, vad_filter=False)
            language = pick_language(probabilities, self.languages)
        model = self._fast if uses_fast_model(language, self.languages) else self._accurate
        segments, _ = model.transcribe(
            audio, language=language, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip(), language
