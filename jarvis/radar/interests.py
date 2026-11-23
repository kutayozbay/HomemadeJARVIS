"""Learn what you are into from what you ask FRIDAY, so the morning brief follows you.

Only topic names and keywords are stored, never your questions. The model sees nothing but your own
recent questions (no web text), and its answer is validated before anything is saved.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from collections.abc import Callable

from .store import RadarStore

WEEK_S = 7 * 86400
MAX_NEW = 5

PROMPT = """Below are things a person asked their assistant during the last week.
Pick up to {n} topics they seem to be actively interested in or learning about right now, topics that would be
good to follow in the news (specific, like "diffusion models" or "Formula 1", never broad like "technology").
Ignore one-off trivia, small talk, and anything private: health, money, relationships, passwords, addresses.
Reply with JSON only, no other text: [{{"topic": "...", "keywords": ["...", "..."]}}]
If nothing qualifies, reply [].

Questions:
{questions}"""


def news_sources(topic: str) -> list[tuple[str, str]]:
    """Where to look for any topic without being told: Google News search (RSS) and Hacker News."""
    q = urllib.parse.quote_plus(topic)
    return [("rss", f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"), ("hn", topic)]


def _clean(text: object, limit: int) -> str | None:
    if not isinstance(text, str):
        return None
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > limit or re.search(r"https?:|www\.|@|\\|<|>", text):
        return None
    return text


def parse_topics(reply: str) -> list[tuple[str, list[str]]]:
    """The topics in the model's reply, validated; anything odd is dropped rather than trusted."""
    start, end = reply.find("["), reply.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return []
    found: list[tuple[str, list[str]]] = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        name = _clean(entry.get("topic"), 40)
        if not name or len(name) < 2:
            continue
        raw = entry.get("keywords")
        keywords = [k for k in (_clean(x, 30) for x in (raw if isinstance(raw, list) else [])) if k][:6]
        found.append((name, keywords or [name.lower()]))
    return found[:MAX_NEW]


def learn(store: RadarStore, ask: Callable[[str], str], questions: list[str], now: float | None = None) -> list[str]:
    """Update the learned topics from recent questions. Returns the names of brand new topics."""
    now = now or time.time()
    store.expire_learned(now)
    text = "\n".join("- " + q.replace("\n", " ")[:200] for q in questions)[:6000]
    if len(questions) < 3:
        return []   # too little to say anything about you
    topics = parse_topics(ask(PROMPT.format(n=MAX_NEW, questions=text)))
    new: list[str] = []
    for name, keywords in topics:
        if store.learn_topic(name, keywords, now):
            topic_id = next(t.id for t in store.topics() if t.name == name)
            for kind, value in news_sources(name):
                store.add_source(topic_id, kind, value)
            new.append(name)
    return new


def learn_from_log(store: RadarStore, log, claude, now: float | None = None) -> list[str]:
    """The daily job: your last seven days of questions in, topics out."""
    now = now or time.time()
    return learn(store, lambda p: claude.ask(p).text, log.recent_prompts(now - WEEK_S), now)
