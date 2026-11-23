"""Build a brief: fetch every source, dedupe, rank, summarise the best few, mark them as delivered."""
from __future__ import annotations

import time
from collections.abc import Callable

from ..backends import Ollama
from .fetch import FetchError, fetch_source, http_get
from .rank import canonical_url, clean_url, drop_near_duplicates, score
from .store import Item, RadarStore, Topic

WINDOW_HOURS = 72


def refresh(store: RadarStore, topic: Topic, get: Callable[[str], bytes], now: float) -> tuple[int, list[str]]:
    """Fetch all sources of a topic. Returns (new item count, human readable source errors)."""
    new, errors = 0, []
    for kind, value in store.sources(topic.id):
        try:
            items = fetch_source(kind, value, get)
        except FetchError as e:
            errors.append(f"{topic.name}/{kind}: {e}")
            continue
        for it in items:
            new += store.upsert_item(topic.id, it.url, canonical_url(it.url), it.title, it.snippet,
                                     it.published, now)
    return new, errors


def build_brief(store: RadarStore, ollama: Ollama | None, *, limit: int = 5,
                get: Callable[[str], bytes] = http_get, now: float | None = None) -> str:
    now = now or time.time()
    topics = store.topics()
    if not topics:
        return "No topics yet. Add one: jarvis radar add \"Formula 1\" --rss <feed-url> --hn \"formula 1\""

    errors: list[str] = []
    candidates: list[tuple[float, Topic, Item]] = []
    for topic in topics:
        _, errs = refresh(store, topic, get, now)
        errors += errs
        ranked = sorted(store.unbriefed(topic.id, now - WINDOW_HOURS * 3600),
                        key=lambda i: score(i, topic.keywords, now), reverse=True)
        for it in drop_near_duplicates(ranked):
            candidates.append((score(it, topic.keywords, now), topic, it))

    candidates.sort(key=lambda c: c[0], reverse=True)
    chosen = candidates[:limit]

    lines = [f"Radar: {len(chosen)} item(s)" if chosen else "Radar: nothing new."]
    for n, (_, topic, it) in enumerate(chosen, 1):
        summary = it.summary
        if summary is None and ollama is not None:
            summary = summarize_item(ollama, it)
            if summary:
                store.save_summary(it.id, summary)
        lines.append(f"{n}. [{topic.name}] {it.title}" + (f"\n   {summary}" if summary else ""))
        lines.append(f"   {clean_url(it.url)}")
    store.mark_briefed([it.id for _, _, it in chosen], now)
    if errors:
        lines.append("Source problems: " + "; ".join(errors[:3]))
    return "\n".join(lines)


def summarize_item(ollama: Ollama, it: Item) -> str | None:
    from .summarize import summarize

    return summarize(ollama, it.title, it.snippet)
