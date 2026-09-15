# PROMPTS.md — prompt design notes

## Files

| File | Role |
|---|---|
| `prompts/classify_v1.txt` | Baseline prompt (naive instruction, chatty model output) |
| `prompts/classify_v2.txt` | Final prompt (format-locked, measurably outperforms v1) |
| `prompts/_iter2_concise.txt` | Interim: v1 + "Please answer concisely." (kept for reproducibility of iteration 2) |
| `prompts/_iter3_rawjson.txt` | Interim: v1 + "Respond with raw JSON only..." (iteration 3) |

## What the model does with them

`stubmodel.py` simulates an instruction-following classifier:

- It classifies the case input by keyword table into `billing`, `technical`,
  `shipping`, `account`, or `general`, and builds a payload with
  `category`, `confidence`, `meta.priority` (`"high"` for billing, else
  `"normal"`), `meta.language`, and a `reason` naming the first matched
  keyword.
- If the prompt contains the phrase "raw JSON only" (case-insensitive), it
  prints exactly one compact JSON object. Otherwise it answers conversationally:
  a "Sure!" preamble, the JSON wrapped in a fenced block with indentation, and
  a "Let me know..." outro.
- At temperature 0 it is fully deterministic. At temperature > 0 a seeded RNG
  sometimes ignores the format instruction and/or picks a wrong category —
  with `--seed`/`--call-index` reproducibly, without them from OS entropy
  (this is what makes `suites/classify_flaky_demo.json` genuinely flaky).

## Why v2 beats v1

Under v1 the chatty output shape breaks five of the six demo cases: the
preamble+fence is not whole-output JSON, so `json_valid` and every
`json_field_equals` fail; `not_contains` catches "Sure!" and "Let me know";
the long conversational wrapper blows the `max_tokens` budgets (64 tokens vs
limits of 40/60); and `equals` can never match. Under v2 the model emits a
single ~132-character JSON line (~33 tokens) that satisfies every assertion.
Case c002 is deliberately unchanged between versions: it only asserts
substring/regex presence, which even the fenced v1 output contains — it
demonstrates that `compare` reports `unchanged` as well as `improved`.

## Iteration history

Four iterations, all real runs, are documented with verbatim reports in
`IMPROVEMENT.md`: baseline (1/5) → conciseness tweak (no change — the
recorded failed attempt) → "raw JSON only" lock (6/0) → full format spec with
key schema and example (6/0, final). The interim prompt files remain in
`prompts/` so the middle iterations can be re-run against
`suites/_iter2.json` / `suites/_iter3.json`.

## Recipe: adding a prompt version

1. Write `prompts/classify_vN.txt`.
2. Copy the closest suite in `suites/`, set `prompt_file` to the new prompt,
   adjust assertions to what the new prompt promises.
3. `python promptlab.py run --suite suites/classify_vN.json --report`.
4. `python promptlab.py compare --baseline <old> --candidate <new>` — watch
   for regressions, cost deltas, and warnings (same prompt_hash means you
   compared a prompt against itself).
5. Record the real output in `IMPROVEMENT.md` (SPEC 13 honesty rule).
