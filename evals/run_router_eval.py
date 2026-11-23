"""Measure the router against labelled cases. Needs Ollama running.

    uv run python evals/run_router_eval.py

The costly mistake is a hard request kept local (a bad answer). The cheap mistake is an easy
request sent to Claude (wasted quota). Both are reported separately.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from jarvis.backends import Ollama
from jarvis.config import Config
from jarvis.router import decide

CASES = Path(__file__).with_name("router_cases.jsonl")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Turkish cases on a cp1252 console
    cfg = Config()
    ollama = Ollama(cfg)
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    ollama.chat("hi", max_tokens=1)  # warm the model so load time is not counted

    hard_kept_local, easy_escalated, correct, total_ms = [], [], 0, 0
    for c in cases:
        t = time.perf_counter()
        d = decide(ollama, c["text"], escalate_below=cfg.escalate_below)
        total_ms += (time.perf_counter() - t) * 1000
        ok = d.route == c["expect"]
        correct += ok
        if not ok and c["expect"] == "claude":
            hard_kept_local.append((c["text"], d))
        elif not ok:
            easy_escalated.append((c["text"], d))
        print(f"{'ok ' if ok else 'BAD'} {d.route:<6} {d.confidence:.2f}  {c['text'][:70]}")

    n = len(cases)
    print(f"\nmodel={cfg.local_model} threshold={cfg.escalate_below}")
    print(f"accuracy: {correct}/{n} = {correct / n:.0%}   avg latency: {total_ms / n:.0f} ms")
    print(f"hard kept local (costly): {len(hard_kept_local)}")
    print(f"easy sent to claude (cheap): {len(easy_escalated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
