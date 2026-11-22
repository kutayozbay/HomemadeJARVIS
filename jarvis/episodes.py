"""Episode log: one row per request, so routing quality and cost can be measured."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    prompt TEXT NOT NULL,
    tier TEXT NOT NULL,            -- rules | local | claude | error
    route TEXT,                    -- router decision (local | claude), null if rules/forced
    confidence REAL,
    latency_ms INTEGER NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    note TEXT
)
"""


@dataclass(frozen=True)
class Episode:
    prompt: str
    tier: str
    latency_ms: int
    route: str | None = None
    confidence: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    note: str | None = None


class EpisodeLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(_SCHEMA)
        self._db.commit()

    def add(self, e: Episode) -> None:
        self._db.execute(
            "INSERT INTO episodes (ts, prompt, tier, route, confidence, latency_ms, tokens_in, tokens_out, cost_usd, note)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.time(), e.prompt, e.tier, e.route, e.confidence, e.latency_ms,
             e.tokens_in, e.tokens_out, e.cost_usd, e.note),
        )
        self._db.commit()

    def stats(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT tier, COUNT(*), CAST(AVG(latency_ms) AS INT), COALESCE(SUM(cost_usd),0),"
            " COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0)"
            " FROM episodes GROUP BY tier ORDER BY COUNT(*) DESC"
        ).fetchall()
        return [dict(tier=t, count=c, avg_ms=a, cost_usd=round(cost, 4), tokens_in=ti, tokens_out=to)
                for t, c, a, cost, ti, to in rows]

    def close(self) -> None:
        self._db.close()
