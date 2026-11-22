"""Orchestration: rules, then router, then the chosen model. Every request is logged."""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import rules
from .backends import SYSTEM_PROMPT, BackendError, ClaudeCLI, Ollama, Reply
from .config import Config
from .episodes import Episode, EpisodeLog
from .router import decide


@dataclass(frozen=True)
class Answer:
    text: str
    tier: str
    latency_ms: int
    note: str | None = None


class Jarvis:
    def __init__(self, cfg: Config | None = None, *, ollama=None, claude=None, log: EpisodeLog | None = None):
        self.cfg = cfg or Config()
        self.ollama = ollama or Ollama(self.cfg)
        self.claude = claude or ClaudeCLI(self.cfg)
        self.log = log or EpisodeLog(self.cfg.db_path)

    def ask(self, text: str, *, force: str | None = None) -> Answer:
        """force: None (auto), 'local' or 'claude'."""
        start = time.perf_counter()
        route = conf = None
        note = None
        reply: Reply | None = None
        tier = "error"
        out = ""

        hit = rules.match(text) if force is None else None
        if hit is not None:
            tier, out = "rules", hit
        else:
            if force is None:
                try:
                    d = decide(self.ollama, text, escalate_below=self.cfg.escalate_below)
                    route, conf = d.route, d.confidence
                except BackendError as e:
                    route, note = "claude", f"router unavailable: {e}"
            else:
                route = force
            try:
                reply, tier = self._run(route, text)
            except BackendError as e:
                # Fall back to the other model rather than failing outright.
                other = "claude" if route == "local" else "local"
                note = f"{route} failed ({e}); fell back to {other}"
                try:
                    reply, tier = self._run(other, text)
                except BackendError as e2:
                    tier, out, note = "error", f"Both models failed: {e2}", f"{note}; {e2}"
            if reply is not None:
                out = reply.text

        ms = int((time.perf_counter() - start) * 1000)
        self.log.add(Episode(
            prompt=text, tier=tier, latency_ms=ms, route=route, confidence=conf,
            tokens_in=reply.tokens_in if reply else None, tokens_out=reply.tokens_out if reply else None,
            cost_usd=reply.cost_usd if reply else None, note=note,
        ))
        return Answer(out, tier, ms, note)

    def _run(self, route: str, text: str) -> tuple[Reply, str]:
        if route == "local":
            return self.ollama.chat(text, system=SYSTEM_PROMPT), "local"
        return self.claude.ask(text), "claude"
