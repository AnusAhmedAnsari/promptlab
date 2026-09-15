#!/usr/bin/env python3
"""stubmodel — the stub model binary promptlab runs against.

Implements the model binary contract from SPEC.md Section 2, exactly:

    python stubmodel.py --prompt <file> --input <text|@file>
      [--temperature 0.0] [--seed N]
      [--max-tokens 256] [--call-index N]

It prints exactly one JSON object to stdout:

    {"output": ..., "tokens_in": N, "tokens_out": N, "finish": ..., "latency_ms": N}

Exit codes: 0 ok, 2 bad arguments, 3 prompt or input file unreadable.

Behavior (an instruction-following classifier stub):
- Deterministic at temperature 0: the output depends only on prompt + input text.
- At temperature > 0 a seeded RNG degrades formatting/classification, so
  flakiness can be exercised. With --seed (and/or --call-index) the RNG is
  seeded and behavior is reproducible; without either it uses OS entropy and
  is genuinely non-deterministic across calls.
- When the prompt contains the instruction "raw JSON only" the stub emits one
  compact JSON object; otherwise it answers conversationally (preamble +
  fenced JSON + outro), which trips format assertions.

Token accounting everywhere (SPEC 5): tokens = ceil(len(text) / 4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time

STRICT_JSON_RE = re.compile(r"raw\s+json\s+only", re.IGNORECASE)

CATEGORY_KEYWORDS = (
    ("billing", ("charged", "charge", "invoice", "refund", "payment",
                 "billing", "subscription", "card", "receipt")),
    ("technical", ("error", "bug", "crash", "login", "log in", "password",
                   "api", "timeout", "500", "not working", "fails", "fail",
                   "sync")),
    ("shipping", ("order", "delivery", "shipping", "ship", "package",
                  "tracking", "arrive", "late", "lost", "parcel")),
    ("account", ("account", "profile", "email", "address", "delete",
                 "sign up", "username", "2fa", "verify")),
)


def token_count(text: str) -> int:
    return math.ceil(len(text) / 4)


def classify(input_text: str):
    lowered = input_text.lower()
    best_category, best_hits, best_score = "general", [], 0
    for category, keywords in CATEGORY_KEYWORDS:
        hits = [keyword for keyword in keywords if keyword in lowered]
        if len(hits) > best_score:
            best_category, best_hits, best_score = category, hits, len(hits)
    confidence = 0.9 if best_score >= 2 else (0.75 if best_score == 1 else 0.5)
    reason = f"matched keyword '{best_hits[0]}'" if best_hits else "no strong keyword signal"
    return best_category, confidence, reason


def stable_hash(prompt_text: str, input_text: str) -> int:
    digest = hashlib.sha256(
        (prompt_text + "\x00" + input_text).encode("utf-8")
    ).hexdigest()
    return int(digest[:16], 16)


def make_rng(prompt_text, input_text, temperature, seed, call_index):
    if temperature <= 0:
        return None
    if seed is None and call_index is None:
        return random.Random()  # OS entropy: genuinely non-deterministic
    base = seed if seed is not None else stable_hash(prompt_text, input_text)
    return random.Random(f"{base}|{call_index}")


def generate(prompt_text, input_text, temperature, rng) -> str:
    category, confidence, reason = classify(input_text)
    strict = STRICT_JSON_RE.search(prompt_text) is not None
    if rng is not None:
        heat = min(temperature, 1.0)
        if rng.random() < heat * 0.5:
            strict = False  # occasionally ignore the format instruction
        if rng.random() < heat * 0.3:
            category = rng.choice([c for c, _ in CATEGORY_KEYWORDS] + ["general"])
            confidence, reason = 0.4, "low-confidence sample at nonzero temperature"
    payload = {
        "category": category,
        "confidence": confidence,
        "meta": {
            "priority": "high" if category == "billing" else "normal",
            "language": "en",
        },
        "reason": reason,
    }
    if strict:
        return json.dumps(payload)
    return (
        "Sure! Here is the classification of your message.\n"
        "```json\n" + json.dumps(payload, indent=2) + "\n```\n"
        "Let me know if you need anything else."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="stubmodel")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=256, dest="max_tokens")
    parser.add_argument("--call-index", type=int, default=None, dest="call_index")
    args = parser.parse_args(argv)  # bad arguments exit 2, per the contract

    try:
        with open(args.prompt, "r", encoding="utf-8") as handle:
            prompt_text = handle.read()
    except OSError as exc:
        print(
            f"stubmodel: cannot read prompt file '{args.prompt}': {exc.strerror or exc}",
            file=sys.stderr,
        )
        return 3
    if args.input.startswith("@"):
        try:
            with open(args.input[1:], "r", encoding="utf-8") as handle:
                input_text = handle.read()
        except OSError as exc:
            print(
                f"stubmodel: cannot read input file '{args.input[1:]}': {exc.strerror or exc}",
                file=sys.stderr,
            )
            return 3
    else:
        input_text = args.input

    rng = make_rng(prompt_text, input_text, args.temperature, args.seed, args.call_index)

    started = time.perf_counter()
    output = generate(prompt_text, input_text, args.temperature, rng)
    finish = "stop"
    if token_count(output) > args.max_tokens:
        output = output[: args.max_tokens * 4]
        finish = "length"
    latency_ms = int((time.perf_counter() - started) * 1000)

    print(json.dumps({
        "output": output,
        "tokens_in": token_count(prompt_text + input_text),
        "tokens_out": token_count(output),
        "finish": finish,
        "latency_ms": latency_ms,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
