"""SQLite storage for radar topics, sources and items (same database file as the episode log)."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    keywords TEXT NOT NULL DEFAULT ''          -- comma separated, lower case
);
CREATE TABLE IF NOT EXISTS radar_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS radar_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES radar_topics(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                        -- rss | hn | arxiv
    value TEXT NOT NULL,
    UNIQUE (topic_id, kind, value)
);
CREATE TABLE IF NOT EXISTS radar_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES radar_topics(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    url_key TEXT NOT NULL,                     -- canonical url, used for dedupe
    title TEXT NOT NULL,
    snippet TEXT NOT NULL DEFAULT '',
    published REAL,
    seen_at REAL NOT NULL,
    summary TEXT,
    briefed_at REAL,
    UNIQUE (topic_id, url_key)
);
"""


@dataclass(frozen=True)
class Topic:
    id: int
    name: str
    keywords: list[str]


@dataclass(frozen=True)
class Item:
    id: int
    topic_id: int
    url: str
    title: str
    snippet: str
    published: float | None
    seen_at: float
    summary: str | None


class RadarStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)

    def add_topic(self, name: str, keywords: list[str]) -> int:
        kw = ",".join(k.strip().lower() for k in keywords if k.strip())
        cur = self._db.execute(
            "INSERT INTO radar_topics (name, keywords) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET keywords = excluded.keywords", (name.strip(), kw))
        self._db.commit()
        return self._db.execute("SELECT id FROM radar_topics WHERE name = ?", (name.strip(),)).fetchone()[0]

    def topics(self) -> list[Topic]:
        rows = self._db.execute("SELECT id, name, keywords FROM radar_topics ORDER BY name").fetchall()
        return [Topic(i, n, [k for k in kw.split(",") if k]) for i, n, kw in rows]

    def add_source(self, topic_id: int, kind: str, value: str) -> None:
        self._db.execute("INSERT OR IGNORE INTO radar_sources (topic_id, kind, value) VALUES (?,?,?)",
                         (topic_id, kind, value.strip()))
        self._db.commit()

    def sources(self, topic_id: int) -> list[tuple[str, str]]:
        return self._db.execute("SELECT kind, value FROM radar_sources WHERE topic_id = ? ORDER BY id",
                                (topic_id,)).fetchall()

    def upsert_item(self, topic_id: int, url: str, url_key: str, title: str, snippet: str,
                    published: float | None, now: float | None = None) -> bool:
        """Insert an item; return True only if it was new for this topic."""
        cur = self._db.execute(
            "INSERT OR IGNORE INTO radar_items (topic_id, url, url_key, title, snippet, published, seen_at)"
            " VALUES (?,?,?,?,?,?,?)", (topic_id, url, url_key, title, snippet, published, now or time.time()))
        self._db.commit()
        return cur.rowcount == 1

    def unbriefed(self, topic_id: int, since: float) -> list[Item]:
        rows = self._db.execute(
            "SELECT id, topic_id, url, title, snippet, published, seen_at, summary FROM radar_items"
            " WHERE topic_id = ? AND briefed_at IS NULL AND COALESCE(published, seen_at) >= ?",
            (topic_id, since)).fetchall()
        return [Item(*r) for r in rows]

    def save_summary(self, item_id: int, summary: str) -> None:
        self._db.execute("UPDATE radar_items SET summary = ? WHERE id = ?", (summary, item_id))
        self._db.commit()

    def mark_briefed(self, item_ids: list[int], now: float | None = None) -> None:
        self._db.executemany("UPDATE radar_items SET briefed_at = ? WHERE id = ?",
                             [(now or time.time(), i) for i in item_ids])
        self._db.commit()

    def get_state(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM radar_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self._db.execute("INSERT INTO radar_state (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        self._db.commit()

    def close(self) -> None:
        self._db.close()
