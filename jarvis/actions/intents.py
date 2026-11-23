"""Instant, model-free recognition of common commands (English and Turkish): music control and "open X"."""
from __future__ import annotations

import re

from . import launcher

VERBS = {
    "pause": {"pause", "stop", "durdur", "duraklat"},
    "play": {"play", "resume", "continue", "oynat", "çal", "devam", "başlat"},
    "next": {"next", "skip", "sonraki", "geç", "atla"},
    "previous": {"previous", "back", "önceki", "geri"},
}
AMBIGUOUS = {"back", "geri", "geç", "başlat", "continue", "devam", "go"}
NOUNS = ("spotify", "music", "song", "track", "playback", "şarkı", "müzi", "parça")
FILLERS = {"the", "this", "that", "my", "please", "lütfen", "bir", "şu", "bu", "it", "now", "a", "me", "can", "you",
           "could", "would", "to", "et", "ı", "i", "u", "ü", "tekrar", "again", "one", "go"}
DOMAIN = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}")


def tokens(text: str) -> list[str]:
    cleaned = re.sub(r"['’]\w*", "", text.lower())          # spotify'ı -> spotify
    return re.findall(r"[a-zçğıöşü0-9]+", cleaned)


def _only_fillers(rest: list[str]) -> bool:
    return all(t in FILLERS or t.startswith(NOUNS) for t in rest)


def media_intent(text: str) -> str | None:
    toks = tokens(text)
    if not toks or len(toks) > 8:
        return None
    words = set(toks)
    if words & {"louder"} or ("volume" in words and words & {"up", "increase", "raise"}) or \
            ("sesi" in words and words & {"aç", "yükselt", "arttır", "artır"}):
        return "volume_up"
    if words & {"quieter", "softer"} or ("volume" in words and words & {"down", "decrease", "lower"}) or \
            ("sesi" in words and words & {"kıs", "azalt", "düşür"}):
        return "volume_down"
    if words & {"mute", "sessize"}:
        return "mute"
    joined = " ".join(toks)
    if re.search(r"\bwhat (is )?playing\b|\b(what|which) (song|track) (is )?(this|that|playing)\b"
                 r"|\bne çalıyor\b|\bbu hangi şarkı\b", joined):
        return "now_playing"
    has_noun = any(t.startswith(NOUNS) for t in toks)
    for cmd, verbs in VERBS.items():
        hits = [t for t in toks if t in verbs]
        if not hits or not _only_fillers([t for t in toks if t not in verbs]):
            continue
        if set(hits) <= AMBIGUOUS and not has_noun:
            continue  # "go back", "geç", "başlat" mean something else without the word music/song
        return cmd
    return None


def open_intent(text: str) -> dict | None:
    t = text.lower().strip(" .!?")
    m = re.match(r"^(?:please |can you |could you )?(?:open|launch|start)\s+(?:the |my )?(.+)$", t)
    name = m.group(1) if m else None
    if not name:
        m = re.match(r"^(.+?)\s+(?:aç|açar mısın|açsana|açabilir misin)$", t)
        name = m.group(1) if m else None
    if not name:
        return None
    name = re.sub(r"['’]\w+$", "", name).strip()
    name = re.sub(r"^(lütfen|bana)\s+", "", name)
    if name in launcher.APPS:
        return {"do": "open_app", "app": name}
    if name in launcher.SITES:
        return {"do": "open_url", "url": launcher.SITES[name]}
    if DOMAIN.fullmatch(name):
        return {"do": "open_url", "url": "https://" + name}
    return None


def parse(text: str) -> dict | None:
    """An action dict for an obvious command, else None (then the language model gets to decide)."""
    cmd = media_intent(text)
    if cmd:
        return {"do": "media", "cmd": cmd}
    return open_intent(text)
