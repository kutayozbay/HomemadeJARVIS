"""Tier 1: deterministic commands. No model, no GPU, instant."""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

HELP = (
    "Commands: /help, /time, /date, /stats\n"
    "Anything else goes to the local model, or to Claude when it looks hard.\n"
    "Force a tier with --local or --claude."
)


def _time() -> str:
    return datetime.now().strftime("%H:%M")


def _date() -> str:
    return datetime.now().strftime("%A, %d %B %Y")


# (pattern, handler). Patterns are matched against the whole, lower-cased, trimmed input.
RULES: list[tuple[re.Pattern[str], Callable[[], str]]] = [
    (re.compile(r"^/help$"), lambda: HELP),
    (re.compile(r"^(/time|saat kaç\??|what time is it\??)$"), _time),
    (re.compile(r"^(/date|bugün ayın kaçı\??|what is the date( today)?\??)$"), _date),
]


def match(text: str) -> str | None:
    """Return the answer if a rule matches, else None."""
    t = text.strip().lower()
    for pattern, handler in RULES:
        if pattern.match(t):
            return handler()
    return None
