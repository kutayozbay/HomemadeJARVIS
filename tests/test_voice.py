"""Voice logic with fake audio, fake speech models and a fake clock: no mic, speakers, GPU or network."""
import pytest

np = pytest.importorskip("numpy")

from jarvis.backends import Reply  # noqa: E402
from jarvis.config import Config  # noqa: E402
from jarvis.core import Jarvis  # noqa: E402
from jarvis.episodes import EpisodeLog  # noqa: E402
from jarvis.voice.audio import calibrate, segment  # noqa: E402
from jarvis.voice.loop import VoiceLoop, strip_wake  # noqa: E402
from jarvis.voice.tts import sentences, speakable  # noqa: E402

N = 480  # one 30 ms block at 16 kHz


def loud():
    return np.full(N, 0.2, dtype="float32")


def quiet():
    return np.full(N, 0.001, dtype="float32")


# ---- end-of-speech detection ----

def test_segment_returns_one_utterance_with_preroll():
    stream = [quiet()] * 5 + [loud()] * 20 + [quiet()] * 40
    audio = segment(iter(stream), threshold=0.05)
    assert audio is not None
    assert 20 * N <= len(audio) <= (5 + 20 + 31) * N  # speech + pre-roll + trailing silence


def test_segment_drops_a_click_and_waits_for_real_speech():
    stream = [quiet()] * 3 + [loud()] * 2 + [quiet()] * 40 + [loud()] * 20 + [quiet()] * 40
    audio = segment(iter(stream), threshold=0.05)
    assert audio is not None and len(audio) >= 20 * N


def test_segment_returns_none_when_the_stream_is_only_silence():
    assert segment(iter([quiet()] * 100), threshold=0.05) is None


def test_segment_is_capped_at_max_length():
    audio = segment(iter([loud()] * 2000), threshold=0.05, max_s=2.0)
    assert audio is not None and len(audio) <= int(2.5 * 16000)


def test_calibrate_sits_above_the_noise_but_has_a_floor():
    assert calibrate(iter([quiet()] * 30)) == 0.012
    noisy = np.full(N, 0.02, dtype="float32")
    assert calibrate(iter([noisy] * 30)) == pytest.approx(0.06)


# ---- what gets spoken ----

def test_speakable_removes_code_links_and_markdown():
    out = speakable("Use **this**:\n```py\nprint(1)\n```\nSee https://example.com now.")
    assert "print" not in out and "http" not in out and "*" not in out
    assert "code on screen" in out


def test_speakable_shortens_long_answers_on_a_sentence_boundary():
    long = " ".join(f"Sentence number {i} is here." for i in range(100))
    out = speakable(long, limit=200)
    assert len(out) < 260 and out.endswith("The rest is on screen.")
    assert sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]


# ---- the loop ----

class FakeOllama:
    def chat(self, user, *, system=None, schema=None, max_tokens=512):
        if schema:
            return Reply('{"route": "local", "confidence": 0.9}')
        return Reply("It is sunny.")


class FakeClaude:
    def ask(self, prompt):
        return Reply("claude")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make_loop(tmp_path, heard, wake=True, language="en"):
    """heard: what the fake transcriber returns for each successive utterance (all in `language`)."""
    cfg = Config(home=tmp_path)
    jarvis = Jarvis(cfg, ollama=FakeOllama(), claude=FakeClaude(), log=EpisodeLog(cfg.db_path))
    queue = list(heard)
    spoken, shown, clock = [], [], Clock()
    loop = VoiceLoop(jarvis, lambda: "audio" if queue else None, lambda _a: (queue.pop(0), language), spoken.append,
                     wake=wake, window_s=10, clock=clock, out=shown.append)
    return loop, spoken, shown, clock


def test_strip_wake():
    assert strip_wake("Friday, what time is it?") == (True, "what time is it?")
    assert strip_wake("what time is it") == (False, "what time is it")
    assert strip_wake("Friday") == (True, "")


@pytest.mark.parametrize("heard", ["Fri day, saat kaç?", "Fraydey saat kaç?", "Freyday, saat kaç?", "friday saat kaç?"])
def test_wake_word_survives_whisper_spelling_variants(heard):
    called, rest = strip_wake(heard)
    assert called and rest == "saat kaç?"


def test_ordinary_words_do_not_wake_it():
    assert strip_wake("fried dough is nice")[0] is False
    assert strip_wake("what is friday")[0] is False


def test_turkish_speech_gets_a_written_answer_that_is_not_spoken(tmp_path):
    loop, spoken, shown, _ = make_loop(tmp_path, ["Friday, bana bir fıkra anlat"], language="tr")
    loop.step()
    assert spoken == []
    assert any(line.startswith("FRIDAY [local]") for line in shown)
    assert any("not spoken" in line for line in shown)


def test_turkish_stop_phrase_ends_the_loop(tmp_path):
    loop, spoken, _, _ = make_loop(tmp_path, ["Friday, dinlemeyi bırak"], language="tr")
    assert loop.step() is False


# ---- languages and voices ----

def test_language_is_picked_among_the_allowed_ones_only():
    from jarvis.voice.stt import pick_language

    probs = [("de", 0.6), ("en", 0.1), ("tr", 0.25)]
    assert pick_language(probs, ("en", "tr")) == "tr"
    assert pick_language(probs, ("en",)) == "en"
    assert pick_language([], ("en", "tr")) == "en"


def test_fast_model_is_only_for_the_main_language():
    from jarvis.voice.stt import uses_fast_model

    assert uses_fast_model("en", ("en", "tr")) is True
    assert uses_fast_model("tr", ("en", "tr")) is False


def test_voice_spec_parsing():
    from jarvis.voice.tts import parse_voice

    assert parse_voice("bm_george") == [("bm_george", 1.0)]
    assert parse_voice("bm_george+bm_lewis") == [("bm_george", 0.5), ("bm_lewis", 0.5)]
    mix = dict(parse_voice("bm_george*0.7+bm_lewis*0.3"))
    assert mix["bm_george"] == pytest.approx(0.7) and mix["bm_lewis"] == pytest.approx(0.3)
    with pytest.raises(ValueError):
        parse_voice("+bm_lewis")


def test_without_the_wake_word_it_stays_silent(tmp_path):
    loop, spoken, shown, _ = make_loop(tmp_path, ["what is the weather like"])
    assert loop.step() is True
    assert spoken == [] and shown == []


def test_verbose_mode_shows_what_was_ignored(tmp_path):
    loop, spoken, shown, _ = make_loop(tmp_path, ["what is the weather like"])
    loop.verbose = True
    loop.step()
    assert spoken == [] and any("ignored, no wake word" in line for line in shown)


def test_wake_word_gets_an_answer_and_opens_a_followup_window(tmp_path):
    loop, spoken, shown, clock = make_loop(tmp_path, ["Friday, is it sunny?", "and tomorrow?", "and later?"])
    loop.run()
    assert spoken[:2] == ["It is sunny.", "It is sunny."]  # the follow-up needed no wake word
    assert any(line.startswith("FRIDAY [local]") for line in shown)


def test_followup_window_expires(tmp_path):
    loop, spoken, _, clock = make_loop(tmp_path, ["Friday, is it sunny?", "and tomorrow?"])
    loop.step()
    clock.t = 60.0
    loop.step()
    assert spoken == ["It is sunny."]  # the late follow-up was ignored


def test_wake_word_alone_says_yes(tmp_path):
    loop, spoken, _, _ = make_loop(tmp_path, ["Friday"])
    loop.step()
    assert spoken == ["Yes?"]


def test_stop_phrase_ends_the_loop(tmp_path):
    loop, spoken, _, _ = make_loop(tmp_path, ["Friday, stop listening"])
    assert loop.step() is False
    assert spoken == ["Going quiet."]


def test_noise_artifacts_are_ignored_and_no_wake_mode_answers_everything(tmp_path):
    loop, spoken, _, _ = make_loop(tmp_path, [".", "is it sunny?"], wake=False)
    loop.run()
    assert spoken == ["It is sunny."]
