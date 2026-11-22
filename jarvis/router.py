"""Tier 2 router: a small local model makes one constrained decision, local or claude."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .backends import Ollama

SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["local", "claude"]},
        "confidence": {"type": "number"},
    },
    "required": ["route", "confidence"],
}

PROMPT = """You route requests for a personal assistant to one of two models.

local  = a small local model. Good for: greetings, simple facts, short definitions, small arithmetic, rewriting or translating a sentence, summarising a short text, casual chat.
claude = a much stronger cloud model. Needed for: writing or debugging code, multi-step reasoning, math proofs, planning, design or architecture, long or nuanced writing, anything needing careful accuracy, anything ambiguous.

Requests that are vague, refer to something not shown ("do this", "fix it"), or lack the context needed to answer must go to claude.
If unsure, choose claude with low confidence.
Reply with JSON: {{"route": "local" or "claude", "confidence": number from 0 to 1}}.

Request:
{request}"""


@dataclass(frozen=True)
class Decision:
    route: str
    confidence: float


def decide(ollama: Ollama, text: str, *, escalate_below: float) -> Decision:
    """Ask the local model. Any malformed answer, or a low confidence, resolves to claude."""
    reply = ollama.chat(PROMPT.format(request=text[:2000]), schema=SCHEMA, max_tokens=40)
    try:
        data = json.loads(reply.text)
        route, conf = data["route"], float(data["confidence"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return Decision("claude", 0.0)
    if route not in ("local", "claude"):
        return Decision("claude", 0.0)
    conf = max(0.0, min(1.0, conf))
    if route == "local" and conf < escalate_below:
        return Decision("claude", conf)
    return Decision(route, conf)
