# 🤖 JARVIS

> A personal assistant platform that runs **local-first**: small jobs stay on my own machine, only hard problems go to a frontier model.

**Status:** v3 is being rebuilt from scratch. The first version was a weekend voice toy; this repo is its successor.

---

## The idea

Most assistant requests are simple — a reminder, a lookup, a summary, a command. Sending all of them to a large cloud model is slow, expensive and unnecessary. JARVIS routes every request through tiers and only escalates when it has to:

```
request ─► 1. rules & commands ─► 2. local LLM ─► 3. Claude ─► 4. tools (MCP)
              free, instant         small GPU       hard jobs     image / video / data
```

| Tier | Handles | Cost |
|---|---|---|
| 1. Rules | `/commands`, regex intents, schedules | none |
| 2. Local LLM (Ollama) | classification, short answers, summaries, "is this hard?" | local GPU |
| 3. Claude | coding, planning, long reasoning, anything ambiguous | API / subscription |
| 4. MCP tools | pluggable capability packs | per tool |

The local model never decides *what to do* freely. It only returns a constrained decision (`route: local | claude`, plus confidence); low confidence escalates.

## Design principles

1. **Platform, not features.** A small core (router, scheduler, memory, policy) plus capability *packs*. A new interest is one folder and one manifest, never a core change.
2. **Untrusted data never reaches a model that holds tools.** Web pages and emails are processed by tool-less, schema-forced calls.
3. **Nothing is sent, posted, bought or traded without an explicit human approval.**
4. **Measure the assistant.** Every request logs which tier answered, cost and latency.
5. **Ship small increments** that get used daily.

Read more in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```
jarvis/
├── docs/ARCHITECTURE.md      design and security model
└── legacy/v2-gemini-voice/   the original voice prototype (Gemini + speech recognition)
```

The v3 core (CLI, router, episode log) will land in `core/`.

## Run the legacy voice prototype

```powershell
cd legacy\v2-gemini-voice
pip install google-generativeai SpeechRecognition pyttsx3 pyaudio
$env:GEMINI_API_KEY = "<your key>"     # never commit keys
python main.py
```

## Security

No secrets live in this repository. Keys are read from environment variables; `.env` files are git-ignored. If you find anything sensitive here, please open an issue.
