"""What FRIDAY may do on the computer. Nothing here touches the real browser, apps or player (see conftest)."""
import pytest

from jarvis import actions
from jarvis.actions import intents, launcher
from jarvis.backends import Reply
from jarvis.config import Config
from jarvis.core import Jarvis
from jarvis.episodes import EpisodeLog


@pytest.mark.parametrize("text,cmd", [
    ("pause the music", "pause"), ("Pause Spotify", "pause"), ("spotify'ı durdur", "pause"),
    ("müziği durdur", "pause"), ("can you please pause the music", "pause"), ("stop", "pause"),
    ("play", "play"), ("resume music", "play"), ("müziği çal", "play"), ("devam et şarkıyı", "play"),
    ("next song", "next"), ("skip", "next"), ("sonraki şarkı", "next"),
    ("previous track", "previous"), ("önceki şarkı", "previous"),
    ("what's playing", "now_playing"), ("what song is this", "now_playing"), ("ne çalıyor", "now_playing"),
    ("turn the volume up", "volume_up"), ("louder", "volume_up"), ("sesi aç", "volume_up"),
    ("volume down", "volume_down"), ("sesi kıs", "volume_down"), ("mute", "mute"),
])
def test_media_commands_are_recognised(text, cmd):
    assert intents.media_intent(text) == cmd


@pytest.mark.parametrize("text", [
    "play Despacito", "play the song Bohemian Rhapsody", "what is the best song of 2020",
    "go back to the previous question", "geç", "başlat", "stop the timer in the kitchen",
    "what is the capital of Italy", "who wrote Dune",
])
def test_other_requests_are_not_mistaken_for_media_commands(text):
    assert intents.media_intent(text) is None


def test_open_commands():
    assert intents.open_intent("open YouTube") == {"do": "open_url", "url": "https://www.youtube.com"}
    assert intents.open_intent("youtube'u aç") == {"do": "open_url", "url": "https://www.youtube.com"}
    assert intents.open_intent("spotify'ı aç") == {"do": "open_app", "app": "spotify"}
    assert intents.open_intent("please open the calculator") == {"do": "open_app", "app": "calculator"}
    assert intents.open_intent("open github.com") == {"do": "open_url", "url": "https://github.com"}
    assert intents.open_intent("open a bank vault") is None           # unknown: the model decides, or nothing happens
    assert intents.open_intent("what is open source") is None


def test_obvious_commands_run_without_a_model(performed):
    assert actions.match("pause the music") == "did pause"
    assert actions.match("open youtube") == "Opening www.youtube.com."
    assert actions.match("tell me a joke") is None
    assert performed == [("media", "pause"), ("browse", "https://www.youtube.com")]


@pytest.mark.parametrize("url", [
    "file:///C:/Windows/system32/config", "javascript:alert(1)", "http://localhost:8080/admin",
    "http://127.0.0.1/x", "http://192.168.1.1/", "http://10.0.0.5", "https://user:pw@example.com/",
    "ftp://example.com", "http://printer.local/", "https://intranet", "", None, 42,
])
def test_dangerous_or_malformed_links_are_refused(url, performed):
    assert launcher.safe_url(url) is None
    assert actions.perform({"do": "open_url", "url": url}) == "I will not open that link."
    assert performed == []


def test_public_links_and_searches_open(performed):
    assert launcher.safe_url("https://example.com/a?b=1") == "https://example.com/a?b=1"
    actions.perform({"do": "web_search", "query": "cute cats", "images": True})
    assert performed == [("browse", "https://www.google.com/search?q=cute+cats&tbm=isch")]


def test_only_listed_apps_open(performed):
    assert actions.perform({"do": "open_app", "app": "spotify"}) == "Opening spotify."
    assert "not allowed" in actions.perform({"do": "open_app", "app": "powershell"})
    assert "not allowed" in actions.perform({"do": "open_app", "app": "cmd /c calc"})
    assert performed == [("start", "spotify:")]


def test_spotify_search_is_url_encoded(performed):
    actions.perform({"do": "spotify_search", "query": "Daft Punk & friends"})
    assert performed == [("start", "spotify:search:Daft%20Punk%20%26%20friends")]


def test_unknown_actions_and_bad_media_commands_do_nothing(performed):
    assert actions.perform({"do": "run", "cmd": "rm -rf /"}) == "I do not know how to do that."
    assert actions.perform({"do": "media", "cmd": "format"}) == "I do not know how to do that."
    assert performed == []


def test_extract_takes_action_lines_out_of_the_spoken_reply():
    reply = ('Opening that for you.\n'
             'ACTION: {"do":"web_search","query":"cats","images":true}\n'
             'ACTION: not json\n'
             'ACTION: {"do":"media","cmd":"pause"}')
    text, acts = actions.extract(reply)
    assert text == "Opening that for you."
    assert [a["do"] for a in acts] == ["web_search", "media"]


def test_extract_allows_at_most_three_actions():
    reply = "\n".join(f'ACTION: {{"do":"media","cmd":"next","n":{i}}}' for i in range(10))
    assert len(actions.extract(reply)[1]) == 3


def test_an_action_line_in_the_middle_of_text_is_still_found_but_prose_is_kept():
    text, acts = actions.extract('Sure. ACTION: {"do":"media","cmd":"pause"} is how I would do it.')
    assert acts == [] and "Sure." in text   # only whole lines count


# ---- through the assistant ----

class ScriptedClaude:
    def __init__(self, reply):
        self.reply = reply

    def ask(self, prompt, model=None):
        return Reply(self.reply)


class NoLocal:
    def chat(self, user, **kw):
        return Reply("local")


def make(tmp_path, reply, **cfg):
    config = Config(home=tmp_path, mode="claude-first", **cfg)
    return Jarvis(config, ollama=NoLocal(), claude=ScriptedClaude(reply), log=EpisodeLog(config.db_path))


def test_claude_can_ask_for_an_action(tmp_path, performed):
    j = make(tmp_path, 'Here you go.\nACTION: {"do":"web_search","query":"capybaras","images":true}')
    a = j.ask("show me pictures of capybaras")
    assert a.tier == "claude" and a.text == "Here you go." and "actions: web_search" in a.note
    assert performed == [("browse", "https://www.google.com/search?q=capybaras&tbm=isch")]


def test_a_dangerous_action_from_claude_is_still_refused(tmp_path, performed):
    j = make(tmp_path, 'Done.\nACTION: {"do":"open_url","url":"file:///C:/secrets.txt"}')
    a = j.ask("open my secrets")
    assert a.text == "Done." and performed == []


def test_actions_can_be_switched_off(tmp_path, performed):
    j = make(tmp_path, 'Done.\nACTION: {"do":"media","cmd":"pause"}', actions=False)
    assert j.ask("pause").tier == "claude"        # not intercepted by the instant rule either
    assert performed == []


def test_forced_local_never_acts(tmp_path, performed):
    j = make(tmp_path, "unused")
    assert j.ask("pause the music", force="local").tier == "local"
    assert performed == []


def test_instant_commands_report_the_action_tier(tmp_path, performed):
    j = make(tmp_path, "unused")
    a = j.ask("pause the music")
    assert a.tier == "action" and a.text == "did pause"
