"""Tier 1b: small tools with live data. Each tool decides by itself whether a request is for it.

A tool only sends what the request needs (for the weather: a city name) and returns plain text.
No model output is ever used to build a request here.
"""
from __future__ import annotations

from ..config import Config
from . import weather


def match(text: str, cfg: Config) -> str | None:
    """Return the tool's answer if some tool handles this request, else None."""
    return weather.answer(text)
