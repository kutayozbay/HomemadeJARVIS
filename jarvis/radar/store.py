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
    origin: str = "manual"      # manual topics never expire; learned ones fade if you stop asking about them
    strength: float = 1.0       # grows each time a learned topic comes up again; multiplies its items' rank


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
        self._migrate()

    def _migrate(self) -> None:
        """Databases made before interest learning get the new columns."""
        have = {row[1] for row in self._db.execute("PRAGMA table_info(radar_topics)")}
        for column, ddl in (("origin", "TEXT NOT NULL DEFAULT 'manual'"), ("strength", "REAL NOT NULL DEFAULT 1.0"),
                            ("last_boost", "REAL")):
            if column not in have:
                self._db.execute(f"ALTER TABLE radar_topics ADD COLUMN {column} {ddl}")
        self._db.commit()

    def learn_topic(self, name: str, keywords: list[str], now: float | None = None) -> bool:
        """Add a learned topic, or strengthen it if it is already there. True only for a brand new topic."""
        now = now or time.time()
        name = name.strip()
        row = self._db.execute("SELECT id, origin, strength, keywords FROM radar_topics WHERE name = ? COLLATE NOCASE",
                               (name,)).fetchone()
        kw = [k.strip().lower() for k in keywords if k.strip()]
        if row is None:
            self._db.execute("INSERT INTO radar_topics (name, keywords, origin, strength, last_boost) "
                             "VALUES (?, ?, 'learned', 1.0, ?)", (name, ",".join(kw), now))
            self._db.commit()
            return True
        topic_id, origin, strength, old_kw = row
        if origin == "learned":
            merged = list(dict.fromkeys([k for k in old_kw.split(",") if k] + kw))[:10]
            self._db.execute("UPDATE radar_topics SET strength = ?, last_boost = ?, keywords = ? WHERE id = ?",
                             (min(5.0, strength + 1.0), now, ",".join(merged), topic_id))
            self._db.commit()
        return False

    def forget(self, name: str) -> bool:
        cur = self._db.execute("DELETE FROM radar_topics WHERE name = ? COLLATE NOCASE", (name.strip(),))
        self._db.commit()
        return cur.rowcount > 0

    def expire_learned(self, now: float | None = None, max_age_days: float = 21.0, max_topics: int = 12) -> list[str]:
        """Drop learned topics you have not touched for a while, and the weakest ones beyond `max_topics`."""
        now = now or time.time()
        dropped: list[str] = []
        stale = self._db.execute("SELECT name FROM radar_topics WHERE origin = 'learned' AND COALESCE(last_boost, 0) < ?",
                                 (now - max_age_days * 86400,)).fetchall()
        for (name,) in stale:
            self.forget(name)
            dropped.append(name)
        extra = self._db.execute("SELECT name FROM radar_topics WHERE origin = 'learned' "
                                 "ORDER BY strength DESC, last_boost DESC LIMIT -1 OFFSET ?", (max_topics,)).fetchall()
        for (name,) in extra:
            self.forget(name)
            dropped.append(name)
        return dropped

    def add_topic(self, name: str, keywords: list[str]) -> int:
        kw = ",".join(k.strip().lower() for k in keywords if k.strip())
        cur = self._db.execute(
            "INSERT INTO radar_topics (name, keywords) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET keywords = excluded.keywords", (name.strip(), kw))
        self._db.commit()
        return self._db.execute("SELECT id FROM radar_topics WHERE name = ?", (name.strip(),)).fetchone()[0]

    def topics(self) -> list[Topic]:
        rows = self._db.execute("SELECT id, name, keywords, origin, strength FROM radar_topics ORDER BY name").fetchall()
        return [Topic(i, n, [k for k in kw.split(",") if k], o, s) for i, n, kw, o, s in rows]

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
