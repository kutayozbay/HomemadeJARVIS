"""Fetch and parse feeds. Everything returned here is untrusted text from the internet."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

MAX_BYTES = 2_000_000
USER_AGENT = "jarvis-radar/0.1"
_TAG = re.compile(r"<[^>]+>")


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeedItem:
    title: str
    url: str
    published: float | None
    snippet: str


def http_get(url: str, timeout: float = 15.0) -> bytes:
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise FetchError(f"Only http(s) URLs are allowed: {url[:80]}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
    except (OSError, ValueError) as e:
        raise FetchError(f"Could not fetch {url[:80]}: {type(e).__name__}") from e
    if len(data) > MAX_BYTES:
        raise FetchError(f"Response too large: {url[:80]}")
    return data


def _clean(text: str | None, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", text or "")).strip()[:limit]


def _ts(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return None


def parse_feed(data: bytes) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom. DTDs and entities are rejected outright (entity-expansion attacks)."""
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise FetchError("Feed rejected: contains a DTD or entity declaration")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise FetchError("Feed is not valid XML") from e

    items: list[FeedItem] = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue

        def child(name: str) -> ET.Element | None:
            return next((c for c in el if c.tag.rsplit("}", 1)[-1] == name), None)

        title = _clean(child("title").text if child("title") is not None else "", 300)
        link = child("link")
        url = (link.get("href") or link.text or "").strip() if link is not None else ""
        date = next((child(n) for n in ("pubDate", "published", "updated", "date") if child(n) is not None), None)
        body = next((child(n) for n in ("description", "summary", "content") if child(n) is not None), None)
        if title and url.startswith(("http://", "https://")):
            items.append(FeedItem(title, url, _ts(date.text) if date is not None else None,
                                  _clean(body.text if body is not None else "")))
    return items


def _parse_hn(data: bytes) -> list[FeedItem]:
    try:
        hits = json.loads(data).get("hits", [])
    except (json.JSONDecodeError, AttributeError) as e:
        raise FetchError("HN response is not valid JSON") from e
    out = []
    for h in hits:
        title = _clean(h.get("title") or h.get("story_title"), 300)
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        if title and str(url).startswith(("http://", "https://")):
            out.append(FeedItem(title, url, h.get("created_at_i"), ""))
    return out


def fetch_source(kind: str, value: str, get: Callable[[str], bytes] = http_get) -> list[FeedItem]:
    q = urllib.parse.quote(value)
    if kind == "rss":
        return parse_feed(get(value))
    if kind == "hn":
        return _parse_hn(get(f"https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=30&query={q}"))
    if kind == "arxiv":
        return parse_feed(get("http://export.arxiv.org/api/query?search_query=all:"
                              f"{q}&sortBy=submittedDate&sortOrder=descending&max_results=20"))
    raise FetchError(f"Unknown source kind: {kind}")
