# 🤖 JARVIS

> A personal assistant platform that runs **local-first**: small jobs stay on my own machine, only hard problems go to a frontier model.

**Status:** v3 core works (rules → local model → Claude, with an episode log). Voice, messaging and capability packs come next. The first version was a weekend voice toy; this repo is its successor.

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

## Quick start

```powershell
winget install Ollama.Ollama
ollama pull qwen3:4b-instruct            # ~2.5 GB, runs on an 8 GB GPU
uv sync

uv run jarvis "what is the capital of Italy?"     # answered locally
uv run jarvis "/time"                              # tier 1, no model at all
uv run jarvis --claude "design a database schema"  # force Claude
uv run jarvis                                      # interactive loop
uv run jarvis /stats                               # per-tier counts, latency, cost
uv run pytest                                      # 25 tests, no GPU or network needed
```

**Claude tier:** Jarvis calls the Claude Code CLI in print mode with all tools disabled. Sign in once with `claude auth login` (set `JARVIS_CLAUDE_CLI` if the executable is not on `PATH`). If Claude or Ollama is unavailable, Jarvis falls back to the other model and says so.

Settings are environment variables: `JARVIS_LOCAL_MODEL`, `JARVIS_ESCALATE_BELOW` (default `0.7`), `JARVIS_KEEP_ALIVE`, `JARVIS_CLAUDE_MODEL`, `JARVIS_HOME` (where the SQLite episode log lives, default `~/.jarvis`).

## Telegram

Talk to Jarvis from your phone. The bot answers **only you**, in a private chat; everyone else is ignored silently.

1. In Telegram, message `@BotFather` → `/newbot` → copy the token.
2. Put the token in `~/.jarvis/.env` (outside the repo, never committed):
   ```
   JARVIS_TELEGRAM_TOKEN=<token from BotFather>
   ```
3. Send your new bot any message, then run `uv run jarvis --telegram-whoami` to see your numeric id, and add it:
   ```
   JARVIS_TELEGRAM_USER_ID=<your numeric id>
   ```
4. `uv run jarvis --telegram` and start chatting. `!claude ...` and `!local ...` force a model; `/stats` shows usage.

The machine running the bot must be on. The bot polls Telegram outbound, so no port is opened.

## Does the router work?

`evals/router_cases.jsonl` holds 24 labelled requests (English and Turkish). On `qwen3:4b-instruct` the router scores **23/24 with no hard request kept local**; the one miss sends an easy rewrite to Claude, which only costs quota. That set is small and was written by the author, so treat it as a regression check, not a benchmark. Run it with `uv run python evals/run_router_eval.py`.

## Repository layout

```
jarvis/
├── jarvis/                   core: config, rules, router, backends, episode log, CLI, Telegram
├── tests/                    unit tests with fake backends
├── evals/                    labelled router cases and the eval runner
├── docs/ARCHITECTURE.md      design and security model
└── legacy/v2-gemini-voice/   the original voice prototype (Gemini + speech recognition)
```

## Run the legacy voice prototype

```powershell
cd legacy\v2-gemini-voice
pip install google-generativeai SpeechRecognition pyttsx3 pyaudio
$env:GEMINI_API_KEY = "<your key>"     # never commit keys
python main.py
```

## Security

No secrets live in this repository. Keys are read from environment variables; `.env` files are git-ignored. If you find anything sensitive here, please open an issue.
