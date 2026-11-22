"""Model backends. Each takes text in and returns a Reply; no tools are ever exposed to either model."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Config, find_claude_cli

SYSTEM_PROMPT = (
    "You are JARVIS, a concise personal assistant. Answer directly and briefly. "
    "Reply in the same language as the user."
)


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class BackendError(RuntimeError):
    """A backend is unreachable or returned something unusable."""


@dataclass(frozen=True)
class Reply:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None


class Ollama:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def chat(self, user: str, *, system: str | None = None, schema: dict | None = None,
             max_tokens: int = 512) -> Reply:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        body = {
            "model": self.cfg.local_model,
            "messages": messages,
            "stream": False,
            "think": False,  # qwen3 would otherwise spend tokens on hidden reasoning
            "keep_alive": self.cfg.keep_alive,
            "options": {"temperature": 0, "num_predict": max_tokens},
        }
        if schema:
            body["format"] = schema
        req = urllib.request.Request(
            f"{self.cfg.ollama_url}/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.local_timeout) as r:
                data = json.load(r)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise BackendError(f"Ollama unreachable: {e}") from e
        text = data.get("message", {}).get("content") or ""
        # Some reasoning models leak their thinking into the answer; keep only what follows it.
        text = _THINK.sub("", text).split("</think>")[-1].strip()
        return Reply(
            text=text,
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
        )


class ClaudeCLI:
    """Calls Claude through the Claude Code CLI in print mode, with every tool disabled."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def ask(self, prompt: str) -> Reply:
        exe = find_claude_cli()
        if not exe:
            raise BackendError("Claude CLI not found. Set JARVIS_CLAUDE_CLI to the claude executable.")
        cmd = [exe, "-p", prompt, "--output-format", "json", "--tools", "",
               "--system-prompt", SYSTEM_PROMPT, "--no-session-persistence",
               "--disable-slash-commands", "--setting-sources", ""]
        if self.cfg.claude_model:
            cmd += ["--model", self.cfg.claude_model]
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_")}
        try:
            # A neutral working directory keeps project instruction files out of the request.
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  timeout=self.cfg.claude_timeout, cwd=tempfile.gettempdir(), env=env)
        except subprocess.TimeoutExpired as e:
            raise BackendError("Claude timed out.") from e
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = None
        if data is None:
            if proc.returncode != 0:
                raise BackendError(f"Claude CLI failed ({proc.returncode}): {(proc.stderr or proc.stdout)[:300]}")
            raise BackendError(f"Claude CLI returned non-JSON output: {proc.stdout[:200]}")
        if data.get("is_error") or proc.returncode != 0:
            msg = str(data.get("result", ""))[:300]
            if "not logged in" in msg.lower():
                raise BackendError(f'Claude CLI is not logged in. Run once: "{exe}" auth login')
            raise BackendError(f"Claude error: {msg}")
        usage = data.get("usage") or {}
        return Reply(
            text=str(data.get("result", "")).strip(),
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            cost_usd=data.get("total_cost_usd"),
        )
