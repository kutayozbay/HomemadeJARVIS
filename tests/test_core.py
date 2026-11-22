"""Core behaviour with fake backends: no GPU, no network, no Claude quota."""
import json

import pytest

from jarvis import rules
from jarvis.backends import BackendError, Reply
from jarvis.config import Config
from jarvis.core import Jarvis
from jarvis.episodes import EpisodeLog
from jarvis.router import decide


class FakeOllama:
    """Answers routing requests with a canned decision and chat requests with 'local-answer'."""

    def __init__(self, route="local", confidence=0.9, raw=None, fail=False):
        self.route, self.confidence, self.raw, self.fail = route, confidence, raw, fail
        self.calls = []

    def chat(self, user, *, system=None, schema=None, max_tokens=512):
        if self.fail:
            raise BackendError("down")
        self.calls.append(("router" if schema else "chat", user))
        if schema:
            text = self.raw if self.raw is not None else json.dumps(
                {"route": self.route, "confidence": self.confidence})
            return Reply(text, 10, 5)
        return Reply("local-answer", 12, 6)


class FakeClaude:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def ask(self, prompt):
        if self.fail:
            raise BackendError("claude down")
        self.calls.append(prompt)
        return Reply("claude-answer", 20, 30, 0.01)


@pytest.fixture
def make(tmp_path):
    def _make(ollama=None, claude=None):
        cfg = Config(home=tmp_path)
        return Jarvis(cfg, ollama=ollama or FakeOllama(), claude=claude or FakeClaude(),
                      log=EpisodeLog(cfg.db_path))
    return _make


def test_rules_match_without_any_model(make):
    o, c = FakeOllama(), FakeClaude()
    a = make(o, c).ask("/help")
    assert a.tier == "rules" and "Commands" in a.text
    assert o.calls == [] and c.calls == []


def test_rule_patterns():
    assert rules.match("  /TIME ")
    assert rules.match("saat kaç?")
    assert rules.match("write me a poem") is None


def test_confident_local_stays_local(make):
    c = FakeClaude()
    a = make(FakeOllama("local", 0.95), c).ask("what is the capital of France?")
    assert a.tier == "local" and a.text == "local-answer"
    assert c.calls == []


def test_low_confidence_escalates(make):
    a = make(FakeOllama("local", 0.4)).ask("hmm")
    assert a.tier == "claude"


def test_claude_route(make):
    a = make(FakeOllama("claude", 0.9)).ask("design a database schema")
    assert a.tier == "claude" and a.text == "claude-answer"


def test_garbage_router_output_goes_to_claude():
    d = decide(FakeOllama(raw="not json"), "x", escalate_below=0.7)
    assert d.route == "claude"
    d = decide(FakeOllama(raw='{"route": "gpt", "confidence": 1}'), "x", escalate_below=0.7)
    assert d.route == "claude"


def test_out_of_range_confidence_is_clamped():
    d = decide(FakeOllama("claude", 7), "x", escalate_below=0.7)
    assert d.confidence == 1.0


def test_ollama_down_falls_back_to_claude(make):
    a = make(FakeOllama(fail=True)).ask("anything")
    assert a.tier == "claude" and "router unavailable" in a.note


def test_claude_down_falls_back_to_local(make):
    a = make(FakeOllama("claude", 0.9), FakeClaude(fail=True)).ask("hard thing")
    assert a.tier == "local" and "fell back" in a.note


def test_both_down_reports_error(make):
    a = make(FakeOllama(fail=True), FakeClaude(fail=True)).ask("x")
    assert a.tier == "error" and "Both models failed" in a.text


def test_force_skips_router_and_rules(make):
    o = FakeOllama()
    a = make(o).ask("/help", force="claude")
    assert a.tier == "claude"
    assert all(kind != "router" for kind, _ in o.calls)


def test_episodes_are_logged(make):
    j = make(FakeOllama("claude", 0.9))
    j.ask("one")
    j.ask("/help")
    stats = {r["tier"]: r for r in j.log.stats()}
    assert stats["claude"]["count"] == 1 and stats["claude"]["cost_usd"] == 0.01
    assert stats["rules"]["count"] == 1


def test_think_tags_are_stripped_from_local_answers():
    from jarvis.backends import _THINK

    leaked = "Okay, let me think.\n</think>\n\nRome"
    assert _THINK.sub("", leaked).split("</think>")[-1].strip() == "Rome"
    closed = "<think>hidden</think>Paris"
    assert _THINK.sub("", closed).split("</think>")[-1].strip() == "Paris"


def test_claude_cli_not_logged_in_gives_actionable_error(monkeypatch, tmp_path):
    import subprocess

    from jarvis import backends

    monkeypatch.setattr(backends, "find_claude_cli", lambda: "claude.exe")
    out = json.dumps({"is_error": True, "result": "Not logged in · Please run /login"})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, out, ""))
    with pytest.raises(BackendError, match="auth login"):
        backends.ClaudeCLI(Config(home=tmp_path)).ask("hi")


def test_claude_cli_parses_a_successful_reply(monkeypatch, tmp_path):
    import subprocess

    from jarvis import backends

    monkeypatch.setattr(backends, "find_claude_cli", lambda: "claude.exe")
    out = json.dumps({"is_error": False, "result": " hello ", "total_cost_usd": 0.002,
                      "usage": {"input_tokens": 5, "output_tokens": 2}})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    r = backends.ClaudeCLI(Config(home=tmp_path)).ask("hi")
    assert (r.text, r.tokens_in, r.tokens_out, r.cost_usd) == ("hello", 5, 2, 0.002)
