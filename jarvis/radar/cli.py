"""`jarvis radar ...`: manage topics and print a brief."""
from __future__ import annotations

import argparse
import sys

from ..backends import Ollama
from ..config import Config
from .brief import build_brief
from .store import RadarStore


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="jarvis radar", description="Interest tracking.")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="add or update a topic and its sources")
    add.add_argument("name")
    add.add_argument("--kw", default="", help="comma separated keywords used for ranking")
    add.add_argument("--rss", action="append", default=[], metavar="URL", help="RSS/Atom feed (repeatable)")
    add.add_argument("--hn", action="append", default=[], metavar="QUERY", help="Hacker News search (repeatable)")
    add.add_argument("--arxiv", action="append", default=[], metavar="QUERY", help="arXiv search (repeatable)")

    sub.add_parser("topics", help="list topics and sources")
    brief = sub.add_parser("brief", help="fetch sources and print the top items")
    brief.add_argument("-n", type=int, default=5, help="maximum items (default 5)")
    brief.add_argument("--no-summary", action="store_true", help="skip the local summaries")

    args = p.parse_args(argv)
    cfg = Config()
    store = RadarStore(cfg.db_path)
    try:
        if args.cmd == "add":
            keywords = [k for k in args.kw.split(",") if k.strip()] or [args.name]
            tid = store.add_topic(args.name, keywords)
            for kind, values in (("rss", args.rss), ("hn", args.hn), ("arxiv", args.arxiv)):
                for v in values:
                    store.add_source(tid, kind, v)
            print(f"Topic '{args.name}' saved with {len(store.sources(tid))} source(s).")
        elif args.cmd == "topics":
            for t in store.topics():
                print(f"{t.name}  (keywords: {', '.join(t.keywords) or '-'})")
                for kind, value in store.sources(t.id):
                    print(f"    {kind}: {value}")
        else:
            print(build_brief(store, None if args.no_summary else Ollama(cfg), limit=args.n))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
