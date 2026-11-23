"""Telegram surface with a fake Bot API: no network."""
import pytest

from jarvis.backends import Reply
from jarvis.config import Config, load_dotenv
from jarvis.core import Jarvis
from jarvis.episodes import EpisodeLog
from jarvis.telegram import TelegramBot, chunk, parse_force, whoami

OWNER = 111


class FakeOllama:
    def chat(self, user, *, system=None, schema=None, max_tokens=512):
        if schema:
            return Reply('{"route": "local", "confidence": 0.9}')
        return Reply("local-answer")


class FakeClaude:
    def ask(self, prompt):
        return Reply("claude-answer", cost_usd=0.01)


@pytest.fixture
def setup(tmp_path):
    sent = []

    def api(method, params):
        sent.append((method, params))
        return {"ok": True, "result": []}

    cfg = Config(home=tmp_path)
    jarvis = Jarvis(cfg, ollama=FakeOllama(), claude=FakeClaude(), log=EpisodeLog(cfg.db_path))
    return TelegramBot("TOKEN", OWNER, jarvis, api), sent


def update(text, sender=OWNER, chat_type="private", chat_id=5):
    return {"update_id": 1, "message": {"text": text, "from": {"id": sender},
                                        "chat": {"id": chat_id, "type": chat_type}}}


def texts(sent):
    return [p["text"] for m, p in sent if m == "sendMessage"]


def test_owner_gets_an_answer(setup):
    bot, sent = setup
    bot.handle(update("what is the capital of Italy?"))
    assert texts(sent) == ["local-answer"]


def test_stranger_is_ignored_silently(setup):
    bot, sent = setup
    bot.handle(update("hello", sender=999))
    assert sent == [] and bot.ignored == 1


def test_group_chat_is_ignored_even_for_owner(setup):
    bot, sent = setup
    bot.handle(update("hello", chat_type="group"))
    assert sent == [] and bot.ignored == 1


def test_non_text_updates_are_skipped(setup):
    bot, sent = setup
    bot.handle({"update_id": 2, "message": {"from": {"id": OWNER}, "chat": {"id": 5, "type": "private"}}})
    bot.handle({"update_id": 3})
    assert sent == []


def test_start_and_instant_commands(setup):
    bot, sent = setup
    bot.handle(update("/start"))
    bot.handle(update("/time"))
    out = texts(sent)
    assert "FRIDAY online" in out[0] and ":" in out[1]


def test_force_prefix(setup):
    bot, sent = setup
    bot.handle(update("!claude explain monads"))
    assert texts(sent) == ["claude-answer"]
    assert parse_force("!local hi") == ("hi", "local")
    assert parse_force("plain") == ("plain", None)


def test_stats_command(setup):
    bot, sent = setup
    bot.handle(update("hello there"))
    bot.handle(update("/stats"))
    assert "local: 1 req" in texts(sent)[-1]


def test_long_answers_are_chunked_on_line_breaks():
    text = "\n".join(["x" * 100] * 120)
    parts = chunk(text, 1000)
    assert all(len(p) <= 1000 for p in parts) and len(parts) > 1
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")
    assert chunk("") == ["(empty answer)"]


def test_whoami_prints_sender_id_and_never_replies(capsys):
    calls = []

    def api(method, params):
        calls.append(method)
        return {"result": [{"update_id": 1, "message": {"from": {"id": 42, "username": "kutay"}}}]}

    whoami("TOKEN", api, once=True)
    assert "42" in capsys.readouterr().out
    assert calls == ["getUpdates"]


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nJARVIS_T1="abc"\nJARVIS_T2=keep-me\n\nbadline\n', encoding="utf-8")
    monkeypatch.delenv("JARVIS_T1", raising=False)
    monkeypatch.setenv("JARVIS_T2", "from-environment")
    load_dotenv(env)
    import os
    assert os.environ["JARVIS_T1"] == "abc"
    assert os.environ["JARVIS_T2"] == "from-environment"
    monkeypatch.delenv("JARVIS_T1", raising=False)


# ---- daily radar brief ----

from datetime import datetime  # noqa: E402


def at(h, m=0, day=23):
    return datetime(2026, 11, day, h, m)


@pytest.fixture
def briefing(setup, monkeypatch):
    bot, sent = setup
    bot._brief = lambda: "Radar: 2 item(s)\n1. [ML] Something"
    return bot, sent


def test_brief_sent_once_per_day_at_the_scheduled_time(briefing):
    bot, sent = briefing
    assert bot.maybe_send_daily_brief(at(7, 29)) is False        # too early
    assert bot.maybe_send_daily_brief(at(7, 30)) is True
    assert bot.maybe_send_daily_brief(at(7, 31)) is False        # already sent today
    assert texts(sent) == ["Radar: 2 item(s)\n1. [ML] Something"]
    assert sent[-1][1]["chat_id"] == OWNER
    assert bot.maybe_send_daily_brief(at(7, 30, day=24)) is True  # next day works


def test_late_start_catches_up_only_within_four_hours(briefing):
    bot, sent = briefing
    assert bot.maybe_send_daily_brief(at(0, 5)) is False
    assert bot.maybe_send_daily_brief(at(11, 45)) is False
    assert bot.maybe_send_daily_brief(at(9, 10)) is True


def test_quiet_briefs_are_not_pushed(setup):
    bot, sent = setup
    bot._brief = lambda: "Radar: nothing new."
    assert bot.maybe_send_daily_brief(at(7, 40)) is False
    assert sent == []
    bot._brief = lambda: "Radar: 1 item(s)"
    assert bot.maybe_send_daily_brief(at(7, 41)) is False        # day already consumed, no retry loop


def test_brief_can_be_disabled(tmp_path):
    cfg = Config(home=tmp_path, brief_time="off")
    jarvis = Jarvis(cfg, ollama=FakeOllama(), claude=FakeClaude(), log=EpisodeLog(cfg.db_path))
    bot = TelegramBot("TOKEN", OWNER, jarvis, lambda m, p: {"result": []})
    bot._brief = lambda: "Radar: 1 item(s)"
    assert bot.maybe_send_daily_brief(at(7, 40)) is False


# ---- CLI guards ----

def test_cli_rejects_a_pasted_command_instead_of_a_token(monkeypatch, capsys):
    from jarvis import cli

    monkeypatch.setenv("JARVIS_TELEGRAM_TOKEN", "cd C:/PythonProjects/jarvis; uv run jarvis --telegram-whoami")
    assert cli._telegram(True) == 2
    assert "does not look like a BotFather token" in capsys.readouterr().err


def test_cli_reports_a_rejected_token_cleanly(monkeypatch, capsys):
    import io
    import urllib.error

    from jarvis import cli, telegram

    monkeypatch.setenv("JARVIS_TELEGRAM_TOKEN", "123456789:" + "A" * 35)

    def boom(token, **kw):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO())

    monkeypatch.setattr(telegram, "whoami", boom)
    assert cli._telegram(True) == 2
    assert "rejected the token (HTTP 401)" in capsys.readouterr().err


def test_dotenv_last_duplicate_wins(tmp_path, monkeypatch):
    import os

    env = tmp_path / ".env"
    env.write_text("JARVIS_T3=<placeholder>\nJARVIS_T3=12345\n", encoding="utf-8")
    monkeypatch.delenv("JARVIS_T3", raising=False)
    load_dotenv(env)
    assert os.environ["JARVIS_T3"] == "12345"
    monkeypatch.delenv("JARVIS_T3", raising=False)
