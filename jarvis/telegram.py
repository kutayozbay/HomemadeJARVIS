"""Telegram surface. Long-polls the Bot API and answers only the owner, in a private chat.

Anyone else is ignored silently: the bot never replies to a stranger, so it leaks nothing about itself.
The token and the owner id come from the environment (see `jarvis.config.load_dotenv`), never from code.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta

from .core import Jarvis

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram limit is 4096 characters per message

HELP = (
    "FRIDAY online.\n"
    "Just write. /time, /date, /stats and /help are instant.\n"
    "Prefix with !strong for the strongest Claude, or !local to force the local model."
)


def chunk(text: str, size: int = MAX_LEN) -> list[str]:
    """Split a long answer on line breaks where possible."""
    text = text.strip() or "(empty answer)"
    parts: list[str] = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > size // 2 else size
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


def parse_force(text: str) -> tuple[str, str | None]:
    for prefix, tier in (("!claude ", "claude"), ("!strong ", "strong"), ("!local ", "local")):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip(), tier
    return text, None


class TelegramBot:
    def __init__(self, token: str, owner_id: int, jarvis: Jarvis,
                 api: Callable[[str, dict], dict] | None = None):
        self.token, self.owner_id, self.jarvis = token, owner_id, jarvis
        self._api = api or self._http
        self.ignored = 0

    def _http(self, method: str, params: dict) -> dict:
        req = urllib.request.Request(
            API.format(token=self.token, method=method), data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
        )
        # Long polling holds the connection for up to `timeout` seconds, so allow extra headroom.
        with urllib.request.urlopen(req, timeout=params.get("timeout", 10) + 15) as r:
            return json.load(r)

    def send(self, chat_id: int, text: str) -> None:
        for part in chunk(text):
            self._api("sendMessage", {"chat_id": chat_id, "text": part})

    def handle(self, update: dict) -> None:
        msg = update.get("message")
        if not msg or "text" not in msg:
            return
        chat, sender = msg.get("chat", {}), msg.get("from", {})
        if chat.get("type") != "private" or sender.get("id") != self.owner_id:
            self.ignored += 1
            return
        text = msg["text"].strip()
        if text == "/start":
            self.send(chat["id"], HELP)
            return
        self._api("sendChatAction", {"chat_id": chat["id"], "action": "typing"})
        if text == "/stats":
            rows = self.jarvis.log.stats()
            lines = [f"{r['tier']}: {r['count']} req, {r['avg_ms']} ms avg, ${r['cost_usd']}" for r in rows]
            self.send(chat["id"], "\n".join(lines) or "No requests logged yet.")
            return
        if text == "/brief":
            self.send(chat["id"], self._brief())
            return
        if text == "/interests" or text.startswith(("/forget ", "/follow ")):
            self.send(chat["id"], self._interests(text))
            return
        question, force = parse_force(text)
        answer = self.jarvis.ask(question, force=force)
        self.send(chat["id"], answer.text)

    def _brief(self) -> str:
        from .backends import Ollama
        from .radar.brief import build_brief
        from .radar.store import RadarStore

        store = RadarStore(self.jarvis.cfg.db_path)
        try:
            return build_brief(store, Ollama(self.jarvis.cfg))
        finally:
            store.close()

    def _interests(self, text: str) -> str:
        from .radar.interests import news_sources
        from .radar.store import RadarStore

        store = RadarStore(self.jarvis.cfg.db_path)
        try:
            command, _, name = text.partition(" ")
            name = name.strip()[:40]
            if command == "/forget":
                return f"Forgot {name}." if store.forget(name) else f"I was not following '{name}'."
            if command == "/follow":
                if not name:
                    return "Say what to follow, e.g. /follow Formula 1"
                topic_id = store.add_topic(name, [name.lower()])
                for kind, value in news_sources(name):
                    store.add_source(topic_id, kind, value)
                return f"Following {name} (it never expires)."
            topics = store.topics()
            if not topics:
                return "No interests yet. Ask me things for a few days, or /follow <topic>."
            return "On your radar:\n" + "\n".join(
                f"- {t.name}" + ("" if t.origin == "manual" else f" (learned, x{t.strength:g})") for t in topics
            ) + "\n/forget <topic> removes one."
        finally:
            store.close()

    def _learn(self) -> list[str]:
        """Update the learned interests from the last week of questions (one Claude call, once a day)."""
        from .radar.interests import learn_from_log
        from .radar.store import RadarStore

        store = RadarStore(self.jarvis.cfg.db_path)
        try:
            return learn_from_log(store, self.jarvis.log, self.jarvis.claude)
        finally:
            store.close()

    def maybe_send_daily_brief(self, now: datetime | None = None) -> bool:
        """Send the radar brief once a day at the configured time. Returns True if a message was sent.

        If the bot starts late it still sends, but only within 4 hours of the scheduled time, so a
        laptop that wakes at midnight does not push a brief. Quiet briefs ("nothing new") are skipped.
        """
        from .radar.store import RadarStore

        now = now or datetime.now()
        try:
            at = datetime.strptime(self.jarvis.cfg.brief_time, "%H:%M").time()
        except ValueError:  # "off" or malformed: feature disabled
            return False
        due = datetime.combine(now.date(), at)
        if not (due <= now < due + timedelta(hours=4)):
            return False
        store = RadarStore(self.jarvis.cfg.db_path)
        try:
            if store.get_state("last_brief_date") == now.date().isoformat():
                return False
            store.set_state("last_brief_date", now.date().isoformat())  # mark first: never retry-loop on errors
        finally:
            store.close()
        try:
            new_topics = self._learn()
        except Exception as e:  # learning is a bonus: it must never block the brief
            print(f"Interest learning failed: {type(e).__name__}: {e}", file=sys.stderr)
            new_topics = []
        text = self._brief()
        if text.startswith(("Radar: nothing new", "No topics yet")):
            return False
        if new_topics:
            text += "\n\nNew on your radar: " + ", ".join(new_topics) + " (/forget <topic> to drop one)"
        self.send(self.owner_id, text)  # a private chat id equals the user id
        return True

    def run(self) -> None:
        offset = 0
        backoff = 1
        print("Telegram bot running. Ctrl+C to stop.", file=sys.stderr)
        while True:
            try:
                self.maybe_send_daily_brief()
            except Exception as e:  # the daily brief must never stop the bot
                print(f"Daily brief failed: {type(e).__name__}: {e}", file=sys.stderr)
            try:
                data = self._api("getUpdates", {"offset": offset, "timeout": 50, "allowed_updates": ["message"]})
                backoff = 1
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                print(f"Telegram poll failed ({type(e).__name__}); retrying in {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    self.handle(update)
                except Exception as e:  # one bad message must not stop the bot
                    print(f"Error handling update: {type(e).__name__}: {e}", file=sys.stderr)


def whoami(token: str, api: Callable[[str, dict], dict] | None = None, *, once: bool = False) -> None:
    """Print the numeric id of whoever messages the bot. Replies to nobody."""
    bot = TelegramBot(token, 0, None, api)  # type: ignore[arg-type]
    offset = 0
    print("Send any message to your bot. Ctrl+C to stop.", file=sys.stderr)
    while True:
        data = bot._api("getUpdates", {"offset": offset, "timeout": 50, "allowed_updates": ["message"]})
        for update in data.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message") or {}
            who = msg.get("from") or {}
            if who.get("id"):
                print(f"user id: {who['id']}  username: @{who.get('username', '-')}")
                if once:
                    return
