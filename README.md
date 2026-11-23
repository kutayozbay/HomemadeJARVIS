# 🤖 JARVIS · FRIDAY

> The project is called JARVIS; the assistant you talk to is **FRIDAY**. A personal assistant platform that runs **local-first**: small jobs stay on my own machine, only hard problems go to a frontier model.

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
uv run pytest                                      # 40 tests, no GPU or network needed
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

## Radar (first capability pack)

Tracks topics you care about and prints a short, deduplicated brief.

```powershell
uv run jarvis radar add "Machine Learning" --kw "llm,transformer,optimizer" --hn "machine learning" --arxiv "optimizer"
uv run jarvis radar add "Formula 1" --kw "f1,formula 1" --rss https://example.com/feed.xml
uv run jarvis radar topics
uv run jarvis radar brief -n 5        # or send /brief to the Telegram bot
```

Sources: RSS/Atom feeds, Hacker News search, arXiv search. Items are deduplicated by canonical URL and by near-identical titles, ranked by keyword hits and a 24 hour recency half-life, and never repeated in a later brief.

Web text is **untrusted**. It is summarised by the local model with no tools, inside an `<untrusted_data>` fence, forced into a one-field JSON schema, then sanitised and truncated. Feeds with DTDs or entity declarations are rejected. Radar runs in-process for now; packaging packs as MCP servers comes later.

## Run it at login

```powershell
.\scripts\install-autostart.ps1            # registers a per-user task that starts the Telegram bot at logon
.\scripts\install-autostart.ps1 -Status
.\scripts\install-autostart.ps1 -Remove
```

The script refuses to install until the token and user id are in `~/.jarvis/.env`. It does not change power settings.

**Keeping the laptop awake** (optional, run it yourself): to keep the bot reachable with the lid closed on AC power, in an elevated PowerShell:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
```

Undo by setting the lid action back to `1` (sleep). A closed lid still produces heat, so keep the vents free.

## Does the router work?

`evals/router_cases.jsonl` holds 24 labelled requests (English and Turkish). On `qwen3:4b-instruct` the router scores **23/24 with no hard request kept local**, at about **250 ms per decision**; the one miss sends an easy rewrite to Claude, which only costs quota. That set is small and was written by the author, so treat it as a regression check, not a benchmark. Run it with `uv run python evals/run_router_eval.py`.

(Performance note: use `127.0.0.1`, not `localhost`, for Ollama on Windows. Python tries IPv6 first and every request paid a ~2 s penalty.)

## Repository layout

```
jarvis/
├── jarvis/                   core: config, rules, router, backends, episode log, CLI, Telegram
│   └── radar/                first pack: topics, feeds, dedupe, ranking, brief
├── scripts/                  install-autostart.ps1
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
