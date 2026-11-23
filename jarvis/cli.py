"""Command line: `jarvis "question"`, `jarvis` for a chat loop, `jarvis /stats`."""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error

from .config import Config, load_dotenv
from .core import Jarvis


def _print_stats(j: Jarvis) -> None:
    rows = j.log.stats()
    if not rows:
        print("No requests logged yet.")
        return
    print(f"{'tier':<8}{'count':>7}{'avg ms':>9}{'cost $':>10}{'tok in':>9}{'tok out':>9}")
    for r in rows:
        print(f"{r['tier']:<8}{r['count']:>7}{r['avg_ms']:>9}{r['cost_usd']:>10}{r['tokens_in']:>9}{r['tokens_out']:>9}")


def _ask(j: Jarvis, text: str, force: str | None) -> None:
    if text.strip() == "/stats":
        _print_stats(j)
        return
    a = j.ask(text, force=force)
    print(a.text)
    print(f"[{a.tier} - {a.latency_ms / 1000:.1f}s]" + (f" {a.note}" if a.note else ""), file=sys.stderr)


def _telegram(whoami_only: bool) -> int:
    from . import telegram

    token = os.environ.get("JARVIS_TELEGRAM_TOKEN", "")
    if not token:
        print("Set JARVIS_TELEGRAM_TOKEN (in ~/.jarvis/.env or the environment).", file=sys.stderr)
        return 2
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
        print("JARVIS_TELEGRAM_TOKEN does not look like a BotFather token (digits, a colon, then letters).\n"
              "Re-run the token command and paste only the token at the 'Bot token:' prompt.", file=sys.stderr)
        return 2
    try:
        if whoami_only:
            telegram.whoami(token, once=True)
            return 0
        owner = os.environ.get("JARVIS_TELEGRAM_USER_ID", "")
        if not owner.isdigit():
            print("Set JARVIS_TELEGRAM_USER_ID to your numeric id (find it with --telegram-whoami).", file=sys.stderr)
            return 2
        j = Jarvis(Config())
        try:
            telegram.TelegramBot(token, int(owner), j).run()
        finally:
            j.log.close()
    except KeyboardInterrupt:
        print()
    except urllib.error.HTTPError as e:
        print("Telegram rejected the token (HTTP %d). Check it in BotFather and store it again." % e.code,
              file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Could not reach Telegram: {type(e).__name__}. Check your connection.", file=sys.stderr)
        return 2
    return 0


def _voice(cfg: Config, wake: bool) -> int:
    from .voice import models

    try:
        from .voice import audio, loop, stt, tts
    except ImportError:
        print("Voice extras are not installed. Run: uv sync --extra voice", file=sys.stderr)
        return 2
    if models.missing(cfg.model_dir):
        print("Voice models are missing. Run once: uv run jarvis --voice-setup (about 340 MB).", file=sys.stderr)
        return 2
    print("Loading speech models ...", file=sys.stderr)
    speaker = tts.Speaker(cfg.model_dir, cfg.tts_voice, cfg.tts_speed)
    transcriber = stt.Transcriber(cfg.stt_model, cfg.stt_languages)
    threshold = cfg.mic_threshold
    if not threshold:
        blocks = audio.mic_blocks()
        try:
            threshold = audio.calibrate(blocks)
        finally:
            blocks.close()  # release the microphone
    j = Jarvis(cfg)

    def listen():
        return audio.segment(audio.mic_blocks(), threshold)

    hint = 'Say "Friday, ..."' if wake else "Just speak"
    print(f"FRIDAY voice ready (speech-to-text on {transcriber.device}, mic threshold {threshold:.3f}). "
          f'{hint}; hears {", ".join(cfg.stt_languages)}; say "stop listening" or press Ctrl+C to quit.',
          file=sys.stderr)
    try:
        loop.VoiceLoop(j, listen, transcriber.transcribe, speaker.speak, wake=wake).run()
    except KeyboardInterrupt:
        print()
    finally:
        j.log.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "radar":  # `radar` is a reserved first word
        from .radar.cli import main as radar_main

        load_dotenv()
        return radar_main(argv[1:])
    p = argparse.ArgumentParser(prog="jarvis", description="Local-first personal assistant.")
    p.add_argument("text", nargs="*", help="what to ask; omit for an interactive loop")
    tier = p.add_mutually_exclusive_group()
    tier.add_argument("--local", action="store_true", help="force the local model")
    tier.add_argument("--claude", action="store_true", help="force Claude")
    p.add_argument("--telegram", action="store_true", help="run the Telegram bot")
    p.add_argument("--telegram-whoami", action="store_true", help="print your Telegram user id, then exit")
    p.add_argument("--voice", action="store_true", help="talk to FRIDAY with the microphone; answers are spoken")
    p.add_argument("--no-wake", action="store_true", help="with --voice: answer everything, no 'Friday' needed")
    p.add_argument("--voice-setup", action="store_true", help="download the text-to-speech model files (~340 MB)")
    args = p.parse_args(argv)
    force = "local" if args.local else "claude" if args.claude else None

    load_dotenv()
    if args.voice_setup:
        from .voice import models

        models.download(Config().model_dir)
        print("Voice models ready.", file=sys.stderr)
        return 0
    if args.voice:
        return _voice(Config(), wake=not args.no_wake)
    if args.telegram_whoami or args.telegram:
        return _telegram(args.telegram_whoami)

    j = Jarvis(Config())
    try:
        if args.text:
            _ask(j, " ".join(args.text), force)
            return 0
        print("FRIDAY ready. /help for commands, Ctrl+C to quit.", file=sys.stderr)
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if line:
                _ask(j, line, force)
    finally:
        j.log.close()


if __name__ == "__main__":
    raise SystemExit(main())
