import pytest


@pytest.fixture(autouse=True)
def router_mode_for_tests(monkeypatch):
    """The real default is claude-first; most tests exercise the local router, so pin it unless a test asks otherwise."""
    monkeypatch.setenv("JARVIS_MODE", "router")
