"""Microphone capture and end-of-speech detection (simple energy gate, no extra model)."""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator

import numpy as np

RATE = 16000
BLOCK_S = 0.03


def rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(block)))) if len(block) else 0.0


def segment(blocks: Iterable[np.ndarray], threshold: float, *, block_s: float = BLOCK_S,
            silence_s: float = 0.7, min_speech_s: float = 0.3, max_s: float = 15.0,
            preroll_blocks: int = 8) -> np.ndarray | None:
    """Consume blocks until one utterance is complete; return its audio, or None if the stream ends.

    An utterance starts at the first loud block (with a little pre-roll so the first syllable is
    kept) and ends after `silence_s` of quiet or `max_s` in total. Clicks shorter than
    `min_speech_s` are dropped.
    """
    pre: deque[np.ndarray] = deque(maxlen=preroll_blocks)
    voiced: list[np.ndarray] = []
    started, loud_blocks, quiet_blocks = False, 0, 0
    for block in blocks:
        loud = rms(block) > threshold
        if not started:
            if loud:
                started, voiced, loud_blocks, quiet_blocks = True, [*pre, block], 1, 0
            else:
                pre.append(block)
            continue
        voiced.append(block)
        loud_blocks, quiet_blocks = (loud_blocks + 1, 0) if loud else (loud_blocks, quiet_blocks + 1)
        if quiet_blocks * block_s >= silence_s or len(voiced) * block_s >= max_s:
            if loud_blocks * block_s >= min_speech_s:
                return np.concatenate(voiced)
            started, voiced = False, []  # a click or cough, not speech
            pre.clear()
    return None


def mic_blocks(rate: int = RATE, block_s: float = BLOCK_S) -> Iterator[np.ndarray]:
    """Yield mono float32 blocks from the default microphone until the generator is closed."""
    import sounddevice as sd

    n = int(rate * block_s)
    with sd.InputStream(samplerate=rate, channels=1, dtype="float32", blocksize=n) as stream:
        while True:
            data, _ = stream.read(n)
            yield data[:, 0].copy()


def calibrate(blocks: Iterator[np.ndarray], count: int = 20, floor: float = 0.012) -> float:
    """Measure the room's noise and return a speech threshold well above it."""
    levels = sorted(rms(b) for _, b in zip(range(count), blocks))
    return max(floor, 3.0 * levels[len(levels) // 2]) if levels else floor
