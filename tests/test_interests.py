"""Learning interests from what you ask, with a fake model: no network."""
import sqlite3
from datetime import datetime

import pytest

from jarvis.backends import Reply
from jarvis.config import Config
from jarvis.core import Jarvis
from jarvis.episodes import Episode, EpisodeLog
from jarvis.radar.interests import learn, learn_from_log, parse_topics
from jarvis.radar.store import RadarStore
from jarvis.telegram import TelegramBot

DAY = 86400
QUESTIONS = ["what is a diffusion model?", "how does classifier free guidance work", "explain DDIM sampling"]
GOOD = '[{"topic": "Diffusion models", "keywords": ["diffusion", "ddim", "guidance"]}]'


@pytest.fixture
def store(tmp_path):
    s = RadarStore(tmp_path / "r.db")
    yield s
    s.close()


def test_parse_accepts_well_formed_topics_even_inside_chatter():
    assert parse_topics("Sure!\n" + GOOD + "\nHope that helps") == [("Diffusion models", ["diffusion", "ddim", "guidance"])]
    assert parse_topics("[]") == [] and parse_topics("no json here") == [] and parse_topics("[1, 2") == []


@pytest.mark.parametrize("bad", [
    '[{"topic": "see https://evil.example", "keywords": ["x"]}]',
    '[{"topic": "mail me@evil.example", "keywords": ["x"]}]',
    '[{"topic": "<script>", "keywords": ["x"]}]',
    '[{"topic": "' + "x" * 80 + '", "keywords": ["x"]}]',
    '[{"topic": 42, "keywords": ["x"]}]', '["just a string"]', '[{"keywords": ["x"]}]',
])
def test_parse_drops_anything_odd_instead_of_trusting_it(bad):
    assert parse_topics(bad) == []


def test_parse_caps_the_number_and_the_keywords():
    many = "[" + ",".join(f'{{"topic": "Topic {i}", "keywords": ' + str([f"k{j}" for j in range(20)]).replace("'", '"') + "}"
                          for i in range(20)) + "]"
    topics = parse_topics(many)
    assert len(topics) == 5 and all(len(kw) == 6 for _, kw in topics)


def test_learning_adds_topics_with_news_sources(store):
    assert learn(store, lambda p: GOOD, QUESTIONS, now=1000.0) == ["Diffusion models"]
    topic = store.topics()[0]
    assert topic.origin == "learned" and topic.strength == 1.0
    kinds = [k for k, _ in store.sources(topic.id)]
    assert kinds == ["rss", "hn"]
    assert "news.google.com/rss/search?q=Diffusion+models" in store.sources(topic.id)[0][1]


def test_seeing_a_topic_again_strengthens_it_and_does_not_report_it_as_new(store):
    learn(store, lambda p: GOOD, QUESTIONS, now=1000.0)
    assert learn(store, lambda p: GOOD, QUESTIONS, now=1000.0 + DAY) == []
    assert store.topics()[0].strength == 2.0


def test_too_few_questions_teach_nothing_and_no_model_call(store):
    calls = []
    assert learn(store, lambda p: calls.append(p) or GOOD, ["hi", "hello"], now=1.0) == []
    assert calls == [] and store.topics() == []


def test_learned_topics_fade_after_three_weeks_but_manual_ones_stay(store):
    learn(store, lambda p: GOOD, QUESTIONS, now=1000.0)
    store.add_topic("Formula 1", ["f1"])
    learn(store, lambda p: "[]", QUESTIONS, now=1000.0 + 22 * DAY)
    assert [t.name for t in store.topics()] == ["Formula 1"]


def test_a_learned_topic_never_overwrites_a_manual_one(store):
    store.add_topic("Diffusion models", ["mine"])
    assert learn(store, lambda p: GOOD, QUESTIONS, now=5.0) == []
    t = store.topics()[0]
    assert t.origin == "manual" and t.keywords == ["mine"] and t.strength == 1.0


def test_the_learned_list_is_capped(store):
    for i in range(15):
        store.learn_topic(f"Topic {i}", ["k"], now=1000.0 + i)
    store.expire_learned(now=1100.0, max_topics=12)
    assert len(store.topics()) == 12


def test_forget(store):
    store.learn_topic("Chess", ["chess"], now=1.0)
    assert store.forget("chess") and not store.forget("chess")


def test_old_databases_get_the_new_columns(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE radar_topics (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
               "keywords TEXT NOT NULL DEFAULT '')")
    db.execute("INSERT INTO radar_topics (name, keywords) VALUES ('Formula 1', 'f1')")
    db.commit()
    db.close()
    s = RadarStore(path)
    t = s.topics()[0]
    assert (t.name, t.origin, t.strength) == ("Formula 1", "manual", 1.0)
    s.close()


def test_recent_prompts_only_include_what_you_asked_the_models(tmp_path):
    log = EpisodeLog(tmp_path / "e.db")
    for prompt, tier in [("what time is it?", "rules"), ("pause", "action"), ("weather", "tool"),
                         ("explain monads", "claude"), ("capital of Italy?", "local")]:
        log.add(Episode(prompt=prompt, tier=tier, latency_ms=1))
    assert set(log.recent_prompts(0)) == {"explain monads", "capital of Italy?"}


def test_the_daily_job_reads_the_log_and_calls_claude_once(tmp_path):
    cfg = Config(home=tmp_path)
    log = EpisodeLog(cfg.db_path)
    for q in QUESTIONS:
        log.add(Episode(prompt=q, tier="claude", latency_ms=1))
    store = RadarStore(cfg.db_path)
    prompts = []

    class Claude:
        def ask(self, prompt):
            prompts.append(prompt)
            return Reply(GOOD)

    assert learn_from_log(store, log, Claude()) == ["Diffusion models"]
    assert len(prompts) == 1 and "diffusion model" in prompts[0] and "Ignore" in prompts[0]
    store.close()


# ---- Telegram ----

class Local:
    def chat(self, user, **kw):
        return Reply("local")


class LearningClaude:
    def ask(self, prompt, model=None):
        return Reply(GOOD)


@pytest.fixture
def bot(tmp_path):
    sent = []
    cfg = Config(home=tmp_path)
    jarvis = Jarvis(cfg, ollama=Local(), claude=LearningClaude(), log=EpisodeLog(cfg.db_path))
    b = TelegramBot("TOKEN", 111, jarvis, lambda m, p: sent.append((m, p)) or {"ok": True, "result": []})
    return b, sent, jarvis


def say(b, text):
    b.handle({"update_id": 1, "message": {"text": text, "from": {"id": 111}, "chat": {"id": 5, "type": "private"}}})


def last_text(sent):
    return [p["text"] for m, p in sent if m == "sendMessage"][-1]


def test_follow_list_and_forget_commands(bot):
    b, sent, _ = bot
    say(b, "/interests")
    assert "No interests yet" in last_text(sent)
    say(b, "/follow Formula 1")
    assert "Following Formula 1" in last_text(sent)
    say(b, "/interests")
    assert "- Formula 1" in last_text(sent)
    say(b, "/forget formula 1")
    assert "Forgot" in last_text(sent)
    say(b, "/forget formula 1")
    assert "was not following" in last_text(sent)


def test_daily_brief_learns_first_and_announces_new_topics(bot):
    b, sent, jarvis = bot
    for q in QUESTIONS:
        jarvis.log.add(Episode(prompt=q, tier="claude", latency_ms=1))
    b._brief = lambda: "Radar: 1 item(s)\n1. [Diffusion models] Something"
    assert b.maybe_send_daily_brief(datetime(2026, 11, 24, 7, 40)) is True
    text = last_text(sent)
    assert "New on your radar: Diffusion models" in text and "/forget" in text


def test_a_learning_failure_never_blocks_the_brief(bot):
    b, sent, _ = bot
    b._learn = lambda: (_ for _ in ()).throw(RuntimeError("claude is down"))
    b._brief = lambda: "Radar: 1 item(s)"
    assert b.maybe_send_daily_brief(datetime(2026, 11, 24, 7, 40)) is True
    assert last_text(sent) == "Radar: 1 item(s)"
