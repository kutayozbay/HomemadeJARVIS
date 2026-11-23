"""Memory, time zone and weather, with a fake weather service: no network."""
import pytest

from jarvis.backends import Reply
from jarvis.config import Config
from jarvis.core import Jarvis
from jarvis.episodes import EpisodeLog
from jarvis.tools import weather


def NOWHERE():
    return None


def HERE():
    return (39.9, 32.8)


def fake_fetch(url):
    if "geocoding" in url:
        return {"results": [{"name": "Ankara", "latitude": 39.9, "longitude": 32.8}]} if "Ankara" in url else {}
    return {"current": {"temperature_2m": 18.4, "weather_code": 2},
            "daily": {"temperature_2m_min": [9.0, 10.0], "temperature_2m_max": [21.2, 23.0],
                      "precipitation_probability_max": [10, 60]}}


def test_weather_in_a_named_city():
    out = weather.answer("What's the weather in Ankara?", NOWHERE, fake_fetch)
    assert out.startswith("Ankara:") and "18 degrees" in out and "partly cloudy" in out and "10 percent" in out


def test_weather_tomorrow_uses_the_second_day():
    out = weather.answer("weather in Ankara tomorrow", NOWHERE, fake_fetch)
    assert "Tomorrow 10 to 23" in out and "60 percent" in out


def test_turkish_weather_without_a_city_uses_where_you_are():
    out = weather.answer("bugün hava nasıl olsun?", HERE, fake_fetch)
    assert "yağış ihtimali" in out and not out.startswith("Ankara")  # 'bugün' is not mistaken for a city


def test_english_weather_without_a_city_uses_where_you_are():
    out = weather.answer("what is the weather like", HERE, fake_fetch)
    assert out.startswith("It is 18 degrees")


def test_turkish_city_before_hava():
    assert weather.find_city("Ankara hava durumu", None) == "Ankara"
    assert weather.find_city("Ankara için hava nasıl", None) == "Ankara"


def test_unknown_location_asks_for_a_city():
    assert "could not work out where you are" in weather.answer("what is the weather", NOWHERE, fake_fetch)


def test_unknown_city_and_network_failure_are_reported_not_raised():
    assert "could not find" in weather.answer("weather in Nowhereville", NOWHERE, fake_fetch)

    def down(url):
        raise OSError("offline")

    assert "could not reach" in weather.answer("weather in Ankara", NOWHERE, down)


@pytest.mark.parametrize("text", ["what temperature does water boil at?", "forecasting is hard",
                                  "hava kirliliği nedir", "what time is it"])
def test_other_questions_do_not_reach_the_weather_tool(text):
    assert weather.answer(text, HERE, fake_fetch) is None


# ---- conversation memory ----

class Recorder:
    """Fake local model that records what it was asked."""
    def __init__(self):
        self.prompts = []

    def chat(self, user, *, system=None, schema=None, max_tokens=512):
        if schema:
            return Reply('{"route": "local", "confidence": 0.9}')
        self.prompts.append(user)
        return Reply(f"answer {len(self.prompts)}")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(tmp_path):
    cfg = Config(home=tmp_path)
    clock, rec = Clock(), Recorder()
    return Jarvis(cfg, ollama=rec, claude=rec, log=EpisodeLog(cfg.db_path), clock=clock), rec, clock


def test_followups_see_the_earlier_conversation(tmp_path):
    j, rec, _ = make(tmp_path)
    j.ask("who wrote Dune?")
    j.ask("and when was it published?")
    assert rec.prompts[0] == "who wrote Dune?"          # nothing earlier yet
    assert "who wrote Dune?" in rec.prompts[1] and "answer 1" in rec.prompts[1]
    assert rec.prompts[1].endswith("and when was it published?")


def test_rule_answers_are_remembered_too(tmp_path):
    j, rec, _ = make(tmp_path)
    first = j.ask("what time is it?")
    assert first.tier == "rules"
    j.ask("is that late?")
    assert first.text in rec.prompts[0]


def test_memory_expires_after_a_long_pause_and_is_capped(tmp_path):
    j, rec, clock = make(tmp_path)
    j.ask("first")
    clock.t = 3600.0
    j.ask("second")
    assert rec.prompts[1] == "second"                    # an hour later: a fresh start
    for i in range(20):
        j.ask(f"q{i}")
    assert rec.prompts[-1].count("User:") <= 6


class ModelAwareClaude:
    def __init__(self):
        self.calls = []

    def ask(self, prompt, model=None):
        self.calls.append(model)
        return Reply("from claude")


class Offline:
    def chat(self, user, *, system=None, schema=None, max_tokens=512):
        return Reply("from local")


class DownClaude:
    def ask(self, prompt, model=None):
        from jarvis.backends import BackendError

        raise BackendError("offline")


def test_claude_first_skips_the_router_and_uses_the_default_model(tmp_path):
    cfg = Config(home=tmp_path, mode="claude-first")
    claude = ModelAwareClaude()
    router_calls = []

    class Local(Offline):
        def chat(self, user, **kw):
            router_calls.append(user)
            return super().chat(user, **kw)

    j = Jarvis(cfg, ollama=Local(), claude=claude, log=EpisodeLog(cfg.db_path))
    a = j.ask("explain monads")
    assert a.tier == "claude" and a.text == "from claude"
    assert claude.calls == [None] and router_calls == []   # default model, router never consulted
    assert cfg.claude_model == "claude-haiku-5-5"


def test_strong_uses_the_strong_model(tmp_path):
    cfg = Config(home=tmp_path, mode="claude-first")
    claude = ModelAwareClaude()
    j = Jarvis(cfg, ollama=Offline(), claude=claude, log=EpisodeLog(cfg.db_path))
    assert j.ask("hard question", force="strong").tier == "claude"
    assert claude.calls == [cfg.strong_model]


def test_claude_first_falls_back_to_local_when_offline(tmp_path):
    cfg = Config(home=tmp_path, mode="claude-first")
    j = Jarvis(cfg, ollama=Offline(), claude=DownClaude(), log=EpisodeLog(cfg.db_path))
    a = j.ask("anything")
    assert a.tier == "local" and a.text == "from local" and "fell back" in a.note


def test_rules_and_tools_still_come_first_in_claude_first_mode(tmp_path):
    cfg = Config(home=tmp_path, mode="claude-first")
    j = Jarvis(cfg, ollama=Offline(), claude=DownClaude(), log=EpisodeLog(cfg.db_path))
    assert j.ask("what time is it?").tier == "rules"


def test_timezone_question_is_answered_by_a_rule(tmp_path):
    j, _, _ = make(tmp_path)
    a = j.ask("on what time zone")
    assert a.tier == "rules" and "time zone" in a.text


def test_weather_goes_through_the_tool_tier(tmp_path, monkeypatch):
    from jarvis.tools import location

    monkeypatch.setattr(weather, "_http_json", fake_fetch)
    monkeypatch.setattr(location, "here", HERE)
    cfg = Config(home=tmp_path)
    j = Jarvis(cfg, ollama=Recorder(), claude=Recorder(), log=EpisodeLog(cfg.db_path))
    a = j.ask("weather today")
    assert a.tier == "tool" and "18 degrees" in a.text


# ---- location (asked when needed, never stored) ----

def test_location_parsing_and_in_memory_cache(monkeypatch):
    from types import SimpleNamespace

    from jarvis.tools import location

    assert location.parse("38.5,26.1\n") == (38.5, 26.1)
    assert location.parse("") is None and location.parse("nan,nan") is None and location.parse("99,0") is None
    monkeypatch.setattr(location, "_cache", None)
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(stdout="38.5,26.1")

    t = [0.0]
    assert location.here(run, lambda: t[0]) == (38.5, 26.1)
    assert location.here(run, lambda: t[0]) == (38.5, 26.1) and len(calls) == 1  # second call served from memory
    t[0] = 3600.0
    location.here(run, lambda: t[0])
    assert len(calls) == 2                                                       # expired after 30 minutes
    monkeypatch.setattr(location, "_cache", None)

