"""Settings, read from environment variables. No secrets are stored in code."""
from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from ~/.jarvis/.env (outside the repo). Real environment variables win."""
    path = path or Path(os.environ.get("JARVIS_HOME", str(Path.home() / ".jarvis"))) / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    values: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")  # a repeated key: the last line wins
    for key, value in values.items():
        os.environ.setdefault(key, value)


def find_claude_cli() -> str | None:
    """Locate the Claude Code executable: env override, PATH, then the desktop app's bundled copy."""
    explicit = os.environ.get("JARVIS_CLAUDE_CLI")
    if explicit:
        return explicit if Path(explicit).exists() else None
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    local = os.environ.get("LOCALAPPDATA")
    if local:
        pattern = str(Path(local) / "Claude-Data" / "*" / "claude-code" / "*" / "*" / "claude.exe")
        found = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if found:
            return found[0]
    return None


@dataclass(frozen=True)
class Config:
    # 127.0.0.1, not "localhost": on Windows, Python tries IPv6 first and waits ~2 s for it to fail on every request.
    ollama_url: str = field(default_factory=lambda: os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434"))
    local_model: str = field(default_factory=lambda: os.environ.get("JARVIS_LOCAL_MODEL", "qwen3:4b-instruct"))
    keep_alive: str = field(default_factory=lambda: os.environ.get("JARVIS_KEEP_ALIVE", "3m"))
    escalate_below: float = field(default_factory=lambda: float(os.environ.get("JARVIS_ESCALATE_BELOW", "0.7")))
    claude_model: str | None = field(default_factory=lambda: os.environ.get("JARVIS_CLAUDE_MODEL") or None)
    home: Path = field(default_factory=lambda: Path(os.environ.get("JARVIS_HOME", str(Path.home() / ".jarvis"))))
    # Daily radar brief on Telegram, local time "HH:MM". Set JARVIS_BRIEF_TIME=off to disable.
    brief_time: str = field(default_factory=lambda: os.environ.get("JARVIS_BRIEF_TIME", "07:30"))
    # Voice (optional extra). Voices are stock Kokoro voices (bm_* British male, bf_* British female), alone or blended.
    stt_model: str = field(default_factory=lambda: os.environ.get("JARVIS_STT_MODEL", "small"))
    # Languages it may hear, first = main one. Each utterance is detected among these, so "en,tr" switches by itself.
    stt_languages: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip() for x in os.environ.get("JARVIS_STT_LANGS", "en,tr").split(",") if x.strip()))
    # A voice is a name or a blend: "bm_george+bm_lewis" (50/50) or "bm_george*0.7+bm_lewis*0.3".
    tts_voice: str = field(default_factory=lambda: os.environ.get("JARVIS_TTS_VOICE", "bm_george+bm_lewis"))
    tts_speed: float = field(default_factory=lambda: float(os.environ.get("JARVIS_TTS_SPEED", "1.1")))
    mic_threshold: float = field(default_factory=lambda: float(os.environ.get("JARVIS_MIC_THRESHOLD", "0")))  # 0 = auto
    local_timeout: float = 120.0
    claude_timeout: float = 300.0

    @property
    def model_dir(self) -> Path:
        return self.home / "models"

    @property
    def db_path(self) -> Path:
        return self.home / "jarvis.db"
