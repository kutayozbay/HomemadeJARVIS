"""URL canonicalisation, near-duplicate removal and scoring. Pure functions, no I/O."""
from __future__ import annotations

import difflib
import math
import urllib.parse

from .store import Item

_TRACKING = ("utm_", "fbclid", "gclid", "mc_", "ref")


def canonical_url(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(_TRACKING)]
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(("https", host, path, urllib.parse.urlencode(sorted(query)), ""))


def clean_url(url: str) -> str:
    """For display: drop tracking parameters and the fragment, keep scheme and host as published."""
    p = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(_TRACKING)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(query), ""))


def score(item: Item, keywords: list[str], now: float, half_life_h: float = 24.0) -> float:
    """Keyword hits (title counts double) times a recency decay with a 24 hour half-life."""
    title, body = item.title.lower(), item.snippet.lower()
    hits = sum(2 for k in keywords if k in title) + sum(1 for k in keywords if k in body)
    age_h = max(0.0, (now - (item.published or item.seen_at)) / 3600)
    return (1 + hits) * math.pow(0.5, age_h / half_life_h)


def drop_near_duplicates(items: list[Item], threshold: float = 0.85) -> list[Item]:
    """Keep the first of any group of near-identical titles (input should be best-first)."""
    kept: list[Item] = []
    for it in items:
        t = it.title.lower()
        if all(difflib.SequenceMatcher(None, t, k.title.lower()).ratio() < threshold for k in kept):
            kept.append(it)
    return kept
