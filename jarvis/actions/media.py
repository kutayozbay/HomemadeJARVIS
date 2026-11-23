"""Control whatever is playing (Spotify first) through the Windows media session. No account, no API key."""
from __future__ import annotations

import asyncio
import sys

PLAYING, PAUSED = 4, 5
VOLUME_KEYS = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}


def _press(vk: int, times: int = 1) -> None:
    import ctypes

    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # key up


async def _session():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

    manager = await Manager.request_async()
    for s in manager.get_sessions():
        if "spotify" in s.source_app_user_model_id.lower():
            return s
    return manager.get_current_session()


async def _name(session) -> str:
    props = await session.try_get_media_properties_async()
    return " - ".join(x for x in (props.artist, props.title) if x) or "the current track"


async def _control(cmd: str) -> str:
    session = await _session()
    if session is None:
        return "Nothing is playing."
    state = int(session.get_playback_info().playback_status)
    if cmd == "now_playing":
        return f"{'Playing' if state == PLAYING else 'Paused on'} {await _name(session)}."
    if cmd == "pause":
        if state != PLAYING:
            return "It is already paused."
        await session.try_pause_async()
        return f"Paused {await _name(session)}."
    if cmd == "play":
        if state == PLAYING:
            return f"Already playing {await _name(session)}."
        await session.try_play_async()
        return f"Playing {await _name(session)}."
    if cmd in ("next", "previous"):
        await (session.try_skip_next_async() if cmd == "next" else session.try_skip_previous_async())
        await asyncio.sleep(0.8)  # let the player publish the new track
        return f"Now {await _name(session)}."
    return f"Unknown media command: {cmd}"


def control(cmd: str) -> str:
    """Run one media command and say what happened. cmd: pause, play, next, previous, now_playing,
    volume_up, volume_down, mute."""
    if sys.platform != "win32":
        return "Media control only works on Windows."
    if cmd in VOLUME_KEYS:
        _press(VOLUME_KEYS[cmd], 5 if cmd != "mute" else 1)  # each press is 2 percent
        return {"volume_up": "Louder.", "volume_down": "Quieter.", "mute": "Muted, or unmuted."}[cmd]
    try:
        return asyncio.run(_control(cmd))
    except Exception as e:  # a missing session or a WinRT hiccup must not crash the assistant
        return f"I could not control the player ({type(e).__name__})."
