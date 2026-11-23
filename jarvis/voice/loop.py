"""The conversation loop: listen, transcribe, ask FRIDAY, speak. Backends are injected, so it is testable."""
from __future__ import annotations

import re
import time
from collections.abc import Callable

from ..core import Jarvis
from .tts import speakable

WAKE_WORDS = ("friday", "fri day", "friday,")
STOP_PHRASES = ("stop listening", "goodbye", "good bye", "exit voice", "shut down voice")


def strip_wake(text: str) -> tuple[bool, str]:
    """Return (was the wake word the first thing said, the rest of the sentence)."""
    low = text.lower().lstrip(" ,.!?")
    for w in WAKE_WORDS:
        if low.startswith(w):
            return True, text.lstrip(" ,.!?")[len(w):].lstrip(" ,.!?:;-")
    return False, text


class VoiceLoop:
    def __init__(self, jarvis: Jarvis, listen: Callable[[], object | None], transcribe: Callable[[object], str],
                 speak: Callable[[str], None], *, wake: bool = True, window_s: float = 12.0,
                 clock: Callable[[], float] = time.monotonic, out: Callable[[str], None] = print):
        self.jarvis, self.listen, self.transcribe, self.speak = jarvis, listen, transcribe, speak
        self.wake, self.window_s, self.clock, self.out = wake, window_s, clock, out
        self._awake_until = 0.0

    def step(self) -> bool:
        """Handle one utterance. Returns False when the loop should end."""
        audio = self.listen()
        if audio is None:
            return False
        heard = self.transcribe(audio).strip()
        if len(re.sub(r"\W", "", heard)) < 2:  # silence artifacts
            return True
        called, rest = strip_wake(heard)
        awake = self.clock() < self._awake_until
        if self.wake and not (called or awake):
            return True  # not for us: stay silent
        if rest.lower().strip(" .!?") in STOP_PHRASES:
            self.out("You: " + heard)
            self.speak("Going quiet.")
            return False
        self.out("You: " + heard)
        if not rest.strip(" .!?"):
            self._awake_until = self.clock() + self.window_s
            self.speak("Yes?")
            return True
        answer = self.jarvis.ask(rest)
        self.out(f"FRIDAY [{answer.tier}]: {answer.text}")
        self.speak(speakable(answer.text))
        self._awake_until = self.clock() + self.window_s  # follow-ups need no wake word for a while
        return True

    def run(self) -> None:
        while self.step():
            pass
