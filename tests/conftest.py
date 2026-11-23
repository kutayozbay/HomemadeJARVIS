import pytest


@pytest.fixture(autouse=True)
def router_mode_for_tests(monkeypatch):
    """The real default is claude-first; most tests exercise the local router, so pin it unless a test asks otherwise."""
    monkeypatch.setenv("JARVIS_MODE", "router")


@pytest.fixture(autouse=True)
def performed(monkeypatch):
    """No test may open a browser, start an app or touch the music player: record what would have happened."""
    from jarvis.actions import launcher, media

    log = []
    monkeypatch.setattr(launcher, "_browse", lambda url: log.append(("browse", url)))
    monkeypatch.setattr(launcher, "_start", lambda target: log.append(("start", target)))
    monkeypatch.setattr(media, "control", lambda cmd: log.append(("media", cmd)) or f"did {cmd}")
    return log
