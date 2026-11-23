"""Download the Kokoro voice model files once (about 340 MB) into ~/.jarvis/models."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from .tts import MODEL_FILE, VOICES_FILE

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {MODEL_FILE: 300_000_000, VOICES_FILE: 20_000_000}  # minimum plausible sizes, to catch truncated downloads


def missing(model_dir: Path) -> list[str]:
    return [name for name in FILES if not (model_dir / name).exists()]


def download(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for name, min_size in FILES.items():
        target = model_dir / name
        if target.exists():
            continue
        print(f"Downloading {name} ...", file=sys.stderr)
        part = target.with_suffix(target.suffix + ".part")
        req = urllib.request.Request(BASE + name, headers={"User-Agent": "jarvis-voice-setup"})
        with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        if part.stat().st_size < min_size:
            part.unlink()
            raise RuntimeError(f"{name} download looks truncated; try again.")
        part.replace(target)
