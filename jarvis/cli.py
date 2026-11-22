"""Command line: `jarvis "question"`, `jarvis` for a chat loop, `jarvis /stats`."""
from __future__ import annotations

import argparse
import sys

from .config import Config
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


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="jarvis", description="Local-first personal assistant.")
    p.add_argument("text", nargs="*", help="what to ask; omit for an interactive loop")
    tier = p.add_mutually_exclusive_group()
    tier.add_argument("--local", action="store_true", help="force the local model")
    tier.add_argument("--claude", action="store_true", help="force Claude")
    args = p.parse_args(argv)
    force = "local" if args.local else "claude" if args.claude else None

    j = Jarvis(Config())
    try:
        if args.text:
            _ask(j, " ".join(args.text), force)
            return 0
        print("JARVIS ready. /help for commands, Ctrl+C to quit.", file=sys.stderr)
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
