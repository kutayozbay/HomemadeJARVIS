"""Text-to-speech with Kokoro (local, ONNX). The voice is a setting, not a clone of anyone."""
from __future__ import annotations

import re
from pathlib import Path

MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"

_CODE = re.compile(r"```.*?```", re.S)
_URL = re.compile(r"https?://\S+")
_MD = re.compile(r"[*_`#>|]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def speakable(text: str, limit: int = 500) -> str:
    """Turn a written answer into something worth saying aloud: no code, links or markdown, and short."""
    text = _CODE.sub(" (code on screen) ", text)
    text = _URL.sub(" link ", text)
    text = _MD.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    kept: list[str] = []
    for sentence in _SENTENCE.split(text):
        if sum(map(len, kept)) + len(sentence) > limit:
            break
        kept.append(sentence)
    return (" ".join(kept) or text[:limit]).strip() + " The rest is on screen."


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text) if s.strip()]


def parse_voice(spec: str) -> list[tuple[str, float]]:
    """'bm_george' -> [('bm_george', 1.0)]; 'a+b' -> equal mix; 'a*0.7+b*0.3' -> weighted. Weights sum to 1."""
    parts = []
    for item in spec.split("+"):
        name, _, weight = item.strip().partition("*")
        if not name:
            raise ValueError(f"bad voice spec: {spec!r}")
        parts.append((name, float(weight) if weight else 1.0))
    total = sum(w for _, w in parts)
    if total <= 0:
        raise ValueError(f"bad voice weights: {spec!r}")
    return [(name, w / total) for name, w in parts]


class Speaker:
    def __init__(self, model_dir: Path, voice: str = "bm_george+bm_lewis", speed: float = 1.1, lang: str = "en-gb"):
        from kokoro_onnx import Kokoro

        self._tts = Kokoro(str(model_dir / MODEL_FILE), str(model_dir / VOICES_FILE))
        mix = parse_voice(voice)
        # A voice is a style vector; a blend is a weighted average of vectors.
        self.voice = sum(self._tts.get_voice_style(name) * w for name, w in mix)
        self.speed, self.lang = speed, lang

    def speak(self, text: str) -> None:
        """Say the text sentence by sentence so the first words start quickly. Ctrl+C stops playback."""
        import sounddevice as sd

        try:
            for part in sentences(text):
                samples, rate = self._tts.create(part, voice=self.voice, speed=self.speed, lang=self.lang)
                sd.play(samples, rate)
                sd.wait()
        except KeyboardInterrupt:
            sd.stop()
            raise
