"""Orchestration: rules, then router, then the chosen model. Every request is logged."""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import rules, tools
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


HISTORY_TURNS = 6          # how many earlier exchanges the models see
HISTORY_IDLE_S = 30 * 60   # a conversation that went quiet this long starts fresh


class Jarvis:
    def __init__(self, cfg: Config | None = None, *, ollama=None, claude=None, log: EpisodeLog | None = None,
                 clock=time.monotonic):
        self.cfg = cfg or Config()
        self.ollama = ollama or Ollama(self.cfg)
        self.claude = claude or ClaudeCLI(self.cfg)
        self.log = log or EpisodeLog(self.cfg.db_path)
        self._clock = clock
        self._history: list[tuple[str, str]] = []
        self._last_turn = 0.0

    def _with_history(self, text: str) -> str:
        """Prepend the recent conversation so follow-ups like 'and tomorrow?' make sense."""
        if self._history and self._clock() - self._last_turn > HISTORY_IDLE_S:
            self._history.clear()
        if not self._history:
            return text
        earlier = "\n".join(f"User: {u}\nFRIDAY: {a[:300]}" for u, a in self._history[-HISTORY_TURNS:])
        return f"Earlier in this conversation:\n{earlier}\n\nThe user now says: {text}"

    def _remember(self, user: str, answer: str) -> None:
        self._history.append((user, answer))
        self._history = self._history[-HISTORY_TURNS:]
        self._last_turn = self._clock()

    def ask(self, text: str, *, force: str | None = None) -> Answer:
        """force: None (auto), 'local', 'claude' (the default Claude model) or 'strong' (the stronger one)."""
        start = time.perf_counter()
        route = conf = None
        note = None
        reply: Reply | None = None
        tier = "error"
        out = ""

        hit = rules.match(text) if force is None else None
        tool_hit = tools.match(text, self.cfg) if force is None and hit is None else None
        if hit is not None:
            tier, out = "rules", hit
        elif tool_hit is not None:
            tier, out = "tool", tool_hit
        else:
            if force is None and self.cfg.mode == "claude-first":
                route = "claude"  # no router call: it only saves time when the local model is allowed to answer
            elif force is None:
                try:
                    d = decide(self.ollama, text, escalate_below=self.cfg.escalate_below)
                    route, conf = d.route, d.confidence
                except BackendError as e:
                    route, note = "claude", f"router unavailable: {e}"
            else:
                route = force
            prompt = self._with_history(text)
            try:
                reply, tier = self._run(route, prompt)
            except BackendError as e:
                # Fall back to the other model rather than failing outright.
                other = "claude" if route == "local" else "local"  # a failed Claude (e.g. offline) falls back to local
                note = f"{route} failed ({e}); fell back to {other}"
                try:
                    reply, tier = self._run(other, prompt)
                except BackendError as e2:
                    tier, out, note = "error", f"Both models failed: {e2}", f"{note}; {e2}"
            if reply is not None:
                out = reply.text

        if tier != "error" and out:
            self._remember(text, out)
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
        if route == "strong":
            return self.claude.ask(text, model=self.cfg.strong_model), "claude"
        return self.claude.ask(text), "claude"
