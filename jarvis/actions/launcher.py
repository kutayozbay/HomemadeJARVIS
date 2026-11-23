"""Open sites and apps. Everything is validated against an allowlist; there is no arbitrary command.

Only http(s) links open, never to this machine or the local network, and apps come from a fixed table.
"""
from __future__ import annotations

import ipaddress
import os
import urllib.parse
import webbrowser

# What "open X" can start. Values are an executable, a protocol handler or a Windows URI.
APPS = {
    "spotify": "spotify:", "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe",
    "explorer": "explorer.exe", "file explorer": "explorer.exe", "paint": "mspaint.exe",
    "task manager": "taskmgr.exe", "settings": "ms-settings:", "terminal": "wt.exe",
    "chrome": "chrome", "edge": "msedge", "vscode": "code", "vs code": "code",
}
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
    "github": "https://github.com", "reddit": "https://www.reddit.com", "x": "https://x.com",
    "twitter": "https://x.com", "netflix": "https://www.netflix.com", "maps": "https://maps.google.com",
    "claude": "https://claude.ai", "wikipedia": "https://www.wikipedia.org", "instagram": "https://www.instagram.com",
    "tiktok": "https://www.tiktok.com", "linkedin": "https://www.linkedin.com",
}


def _browse(url: str) -> None:
    webbrowser.open(url)


def _start(target: str) -> None:
    os.startfile(target)  # noqa: S606 - target always comes from APPS or is a spotify: search URI


def safe_url(url: object) -> str | None:
    """The url if it is a plain http(s) link to a public host, else None."""
    if not isinstance(url, str) or len(url) > 2000:
        return None
    parts = urllib.parse.urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
        return None
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url.strip() if "." in host else None   # a real domain name has a dot
    return None if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved) else url.strip()


def search_url(query: str, images: bool = False) -> str:
    q = urllib.parse.quote_plus(query.strip()[:300])
    return f"https://www.google.com/search?q={q}" + ("&tbm=isch" if images else "")


def open_url(url: object) -> str:
    safe = safe_url(url)
    if not safe:
        return "I will not open that link."
    _browse(safe)
    return f"Opening {urllib.parse.urlsplit(safe).hostname}."


def web_search(query: object, images: bool = False) -> str:
    if not isinstance(query, str) or not query.strip():
        return "What should I search for?"
    _browse(search_url(query, bool(images)))
    return f"Searching for {query.strip()[:80]}."


def open_app(app: object) -> str:
    name = str(app).lower().strip()
    if name not in APPS:
        return f"I am not allowed to open {name[:40]}."
    _start(APPS[name])
    return f"Opening {name}."


def spotify_search(query: object) -> str:
    if not isinstance(query, str) or not query.strip():
        return "What should I look for on Spotify?"
    _start("spotify:search:" + urllib.parse.quote(query.strip()[:200]))
    return f"Searching Spotify for {query.strip()[:80]}."
