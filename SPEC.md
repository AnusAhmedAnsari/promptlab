# SPEC.md — promptlab

Status: FINAL for v1. This document is FULLY SELF-CONTAINED. Every schema, contract, and format below is the literal, exact specification — nothing is a summary or a reference to an external document. Do not reconstruct, guess, or "fill in" any part of this from assumption. If any part seems incomplete, stop and ask rather than inventing a replacement.

---

## 1. Purpose

`promptlab` is a CLI harness that runs prompt test suites against a model binary (`stubmodel.py`, or a compatible swap-in binary), evaluates assertions on the output, and reports results — including flaky (non-deterministic) behavior and regressions between prompt versions.

---

## 2. The model binary contract (EXACT — this is `stubmodel.py`'s real CLI)

```
python stubmodel.py --prompt <file> --input <text|@file>
  [--temperature 0.0] [--seed N]
  [--max-tokens 256] [--call-index N]
```

- `--prompt <file>`: path to the prompt file (plain text)
- `--input <text|@file>`: either a literal input string, OR `@path/to/file` to read input from a file
- `--temperature`: float, default 0.0
- `--seed`: optional int, for reproducibility above temperature 0
- `--max-tokens`: int, default 256
- `--call-index`: optional int (pass through only if the suite specifies one, otherwise omit)

It prints exactly ONE JSON object to stdout:

```json
{"output": "...", "tokens_in": 92, "tokens_out": 24, "finish": "stop", "latency_ms": 340}
```

Exit codes from the model binary itself: `0` ok · `2` bad arguments · `3` prompt or input file unreadable.

**Model binary location (locked):** the harness looks for the model binary in this order: (1) the `PROMPTLAB_MODEL_BIN` environment variable if set, (2) `stubmodel.py` in the current working directory, (3) `stubmodel.py` in the same directory as the suite file. If none exist, this is a model invocation failure (exit 3, Section 3), with a message naming all three locations checked. Invoke `.py` binaries as `[sys.executable, path, ...args]`; invoke any other binary directly as `[path, ...args]`.

**Subprocess timeout (locked, mandatory):** every model invocation runs with a **30-second timeout** (`subprocess.run(..., timeout=30)`). If the process does not return within 30 seconds, kill it and treat it as a model invocation failure: exit 3, message `"model binary did not respond within 30s"`. This applies uniformly to `stubmodel.py` and any swapped-in binary. Never invoke the model without a timeout — an unresponsive subprocess must not be able to hang the entire harness.

**Do not invent different flag names.** The harness invokes the binary using exactly these flags: `--prompt`, `--input`, `--temperature`, `--max-tokens` (and `--seed`/`--call-index` only if the suite specifies them). Never `--prompt-file` or `--input-file` — those do not exist in this contract.

The `--input` value: if the suite's case input is a plain string, pass it directly as the `--input` value. If the suite's case input is `{"file": "path"}`, resolve that path (Section 4) and pass it as `--input @<resolved_absolute_path>`.

---

## 3. CLI Contract for `promptlab` itself (exact — do not deviate)

```
promptlab run --suite <file> [--runs N] [--out report.json] [--report]
promptlab compare --baseline <report.json> --candidate <report.json> [--out diff.json]
promptlab doctor
```

### Exit codes (exact meaning)

| Code | Meaning | Trigger |
|---|---|---|
| 0 | Success | All cases passed (run), or command completed normally (compare/doctor) |
| 1 | Bad usage / malformed input | Bad CLI args, malformed suite JSON, invalid suite structure |
| 2 | Cases failed | One or more cases failed or were flaky — a result, not a crash |
| 3 | Model invocation failure | The model binary could not be started/executed, or its output could not be parsed |
| 4 | File I/O failure | A suite file or report file could not be read (missing, unreadable, wrong permissions) |

Exit code 2 must never be conflated with exit code 1.

### `run` output behavior (locked — exact for every flag combination)

| Flags | stdout | stderr | file written |
|---|---|---|---|
| (none) | full report JSON | — | — |
| `--out FILE` | — | short human summary | report JSON → FILE |
| `--report` | full report JSON + human summary appended after it | — | — |
| `--out FILE --report` | human summary | — | report JSON → FILE |

In every case, the exit code (0/2/3/4) is determined by the run's results regardless of which flags were passed.

---

## 4. Suite Format (EXACT — this is the literal format, nothing else)

```json
{
  "name": "classify-smoke",
  "prompt_file": "prompts/classify_v1.txt",
  "model": { "temperature": 0.0, "max_tokens": 256 },
  "runs": 1,
  "cases": [
    {
      "id": "c001",
      "input": "I was charged twice for invoice 7",
      "assert": [
        { "type": "json_valid" },
        { "type": "json_field_equals", "field": "category", "value": "billing" },
        { "type": "not_contains", "value": "Sure" },
        { "type": "max_tokens", "value": 40 },
        { "type": "finish_is", "value": "stop" }
      ]
    }
  ]
}
```

Field notes:
- `name`: string, required, the suite's name (used in reports).
- `prompt_file`: string path, required.
- `model`: optional object, `{ "temperature": float, "max_tokens": int }`. Defaults: `temperature=0.0`, `max_tokens=256`.
- `runs`: optional positive integer, default `1`. `--runs` on the CLI overrides this when both are present.
- `cases`: required list (can be an empty list — valid, produces a report with zero cases).
- Each case: `id` (required, non-empty string, unique within the suite), `input` (required — either a plain string, or `{"file": "path"}`), `assert` (required list — can be an empty list; that case auto-passes every run).

**Path resolution:** `input.file` and `prompt_file` are resolved relative to the suite JSON file's own directory, never relative to the current working directory.

**`--runs` / `runs` validation (locked):** the effective run count (CLI `--runs` if given, else the suite's `runs` field, else default `1`) must be a **positive integer (>= 1)**. A value of `0`, a negative number, or a non-integer is a bad-usage error: exit 1, message naming the invalid value. This must be checked before any model invocation — never divide by a run count without validating it first.

**Validation (any violation ⇒ exit 1, with a message naming the specific field and problem):**
- Missing `name`, `prompt_file`, or `cases` key at the top level.
- A case missing `id`, `input`, or `assert`.
- `input` that is neither a string nor an object with a `file` key.
- An assertion object with a `type` that is not one of the 8 registered types (Section 6).
- An assertion missing a required field for its type (Section 6 table).

---

## 5. Report Schema (EXACT — this is the literal format judges diff byte-for-byte at temperature 0)

```json
{
  "suite": "classify-smoke",
  "prompt_file": "prompts/classify_v1.txt",
  "prompt_hash": "a19f40cc21b8",
  "runs": 3,
  "model": { "temperature": 0.4, "max_tokens": 256 },
  "totals": {
    "cases": 20, "passed": 16, "failed": 3, "flaky": 1,
    "tokens_in": 4120, "tokens_out": 980, "wall_ms": 8640
  },
  "cases": [
    {
      "id": "c001",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 21,
      "assertions": [ { "type": "json_valid", "passed": 3, "failed": 0 } ],
      "failures": []
    }
  ]
}
```

- `prompt_hash`: the first 12 hex characters of `sha256(prompt_file_bytes)`.
- `totals.cases/passed/failed/flaky`: counts of cases by their final status (Section 7 policy) — these four numbers must always sum to `totals.cases`.
- `totals.tokens_in/tokens_out`: summed across every run of every case in the suite.
- `totals.wall_ms`: total wall-clock time for the whole `run` invocation. **Volatile field.**
- Per case: `assertions` is a list with one entry **per assertion type used in that case**, each with `passed`/`failed` = count of runs where that assertion passed/failed. `failures` is detailed per-failure entries (Section 8).
- `tokens_out_avg`: per-case average of `tokens_out` across its runs.

**Determinism rule:** at `--temperature 0.0`, running the same suite twice must produce byte-identical reports except for `totals.wall_ms` (the only volatile field — `latency_ms` from the model is not part of this report schema, so it cannot leak in). Use a fixed, explicit key order when serializing.

Token formula (used everywhere, including reports): `tokens = math.ceil(len(text) / 4)`.

---

## 6. Assertion Types — the exact 8, no substitutes

| Type | Fields | Passes when |
|---|---|---|
| `contains` | `value`, optional `ignore_case` | The output contains `value` |
| `not_contains` | `value`, optional `ignore_case` | The output does not contain `value` |
| `equals` | `value`, optional `normalize` | Output equals `value`. `normalize: true` strips and collapses whitespace before comparing |
| `matches` | `pattern` | `re.search(pattern, output)` finds a match |
| `json_valid` | — | The output parses as JSON (see fenced-JSON rule below) |
| `json_field_equals` | `field`, `value` | A dotted path (e.g. `meta.priority`) into the parsed JSON resolves to `value` |
| `max_tokens` | `value` | The model's reported `tokens_out` for that run is `<= value` |
| `finish_is` | `value` | The model's reported `finish` field equals `value` (one of `"stop"`, `"length"`, `"refusal"`) |

Do not add `min_length`/`max_length` or any other type not in this table.

**Evaluation model:** every assertion in a case's `assert` list is evaluated on every run — evaluation does not stop at the first failure. A run counts as passed only if all assertions in that case pass on that run.

**Fenced JSON decision (locked):** the model may wrap JSON output in a Markdown code fence. Write ONE shared helper, e.g. `extract_json(text) -> Optional[dict]`, that: strips a fence (opening ` ``` ` or ` ```json ` line and closing ` ``` `, if present, else uses the raw text), then attempts `json.loads`. Both `json_valid` and `json_field_equals` must call this same helper — never implement fence-handling twice. If parsing fails, both fail for that run.

**`json_field_equals` comparison rule (locked):** after resolving the dotted path, compare the resolved value to the suite's `value` using strict Python `==` with **no type coercion**. A JSON number resolved from the output does not equal a JSON string in the suite even if they "look the same" (e.g. `1 != "1"`). A type/value mismatch is simply a failed assertion — not an error.

**`matches` regex validation timing (locked):** all `matches` patterns across the entire suite are compiled (`re.compile`) at suite **load time**, before any model invocation happens. If any pattern is invalid, the suite fails immediately with exit 1 — zero model calls are made. Do not defer regex validation to when the case actually runs.

---

## 7. Flaky Policy (locked)

For a case run `N` times:
- `status = "pass"` if `pass_rate == 1.0`
- `status = "fail"` if `pass_rate == 0.0`
- `status = "flaky"` otherwise (any mix)

Applies uniformly regardless of `N`. `pass_rate = passed_runs / total_runs`.

---

## 8. Failure Detail (the `failures` field)

Each entry:

```json
{
  "run_index": 2,
  "assertion_type": "json_field_equals",
  "expected": "billing",
  "actual": "<first 200 chars, '...' appended if longer>",
  "message": "short human-readable reason"
}
```

One entry per failing (assertion, run) pair. `run_index` is 1-based.

---

## 9. Comparison Logic (`compare`)

- **Regression:** any decrease in a case's `pass_rate` between baseline and candidate = regression, even if `status` is unchanged in both.
- Classification per case: `regressed`, `improved`, `unchanged`, `new`, `removed`.
- **Cost delta:** `totals.tokens_in`/`totals.tokens_out` — delta and percentage change, candidate minus baseline.
- **Mandatory warnings** (printed, not blocking): baseline/candidate share the same `prompt_hash`; different `suite` names; different `model` settings.

### `compare` output (locked — exact)

Human summary always goes to stdout: any warnings first (one `WARNING: ...` line each), then one line per case as `<id>: <classification> (<baseline_pass_rate> -> <candidate_pass_rate>)` (for `new`/`removed` cases show `n/a` for the missing side), then a cost-delta line, then a one-line summary count.

If `--out FILE` is given, additionally write this exact JSON to FILE:

```json
{
  "baseline": "baseline.json",
  "candidate": "candidate.json",
  "warnings": ["..."],
  "cost": {
    "tokens_in":  {"baseline": 0, "candidate": 0, "delta": 0, "pct_change": 0.0},
    "tokens_out": {"baseline": 0, "candidate": 0, "delta": 0, "pct_change": 0.0}
  },
  "cases": {
    "c001": {"classification": "regressed", "baseline_pass_rate": 1.0, "candidate_pass_rate": 0.9}
  },
  "summary": {"regressed": 0, "improved": 0, "unchanged": 0, "new": 0, "removed": 0}
}
```

`pct_change = round(delta / baseline * 100, 2)`; if `baseline == 0`, `pct_change` is `0.0` when `delta == 0`, else `null`. `compare` always exits 0 when it completes (Section 3) — a regression is reported, not a failure exit.

---

## 10. `doctor` (all four checks required)

Print one PASS/FAIL line for each, in this order: `[PASS|FAIL] python`, `[PASS|FAIL] model`, `[PASS|FAIL] suites`, `[PASS|FAIL] assertions`.

1. **python** — passes if the running interpreter is 3.10+.
2. **model** — passes if the model binary (Section 2's location rule) responds to a minimal real invocation (e.g. a trivial prompt/input) with valid JSON output.
3. **suites** — passes if at least one `*.json` file exists under `./suites/` (if that directory exists) or directly in the current working directory.
4. **assertions** — passes if all 8 types from Section 6 are registered/importable in the running code.

`doctor` exits 0 when it completes; the PASS/FAIL lines are the deliverable, not the exit code.

---

## 11. Error Handling (crash-proofing)

Each of the following produces a single-line message on stderr and the correct exit code — never a raw traceback: missing/unreadable prompt file, missing/unreadable input file, model binary not found/not executable/crashed, invalid regex in `matches`, malformed/unparseable suite or report JSON, unknown assertion type. Wrap each failure point in its own specific `try/except` — the message must name what failed and where.

---

## 12. Model Invocation Rule

Invoke the model binary **only via subprocess**, using the exact flags in Section 2. Never import it, never reimplement its logic, never assume anything about its output beyond the documented JSON contract (`output`, `tokens_in`, `tokens_out`, `finish`, `latency_ms`). The harness must work unmodified with a different binary implementing the same CLI contract.

---

## 13. IMPROVEMENT.md Honesty Rule

Every iteration must be backed by a real `promptlab run` execution — actual report output pasted in, not invented numbers. At least four iterations; at least one must be a change that did not help.

---

## 14. Development Process Rule (git discipline)

First commit contains `SPEC.md` only — zero code. Design changes are committed to `SPEC.md` before the corresponding code change.

---

## 15. Definition of Done (v1)

1. All eight assertion types from Section 6 (exact names, exact fields) — no substitutes.
2. `run`, `compare`, `doctor` per Sections 3, 9, 10 exactly.
3. Report schema matches Section 5 exactly, including `totals.cases/passed/failed/flaky` and per-case `assertions` breakdown.
4. Model invoked via the exact flags in Section 2 — `--prompt`, `--input`, `--temperature`, `--max-tokens`.
5. Temperature-0 determinism: two runs of the same suite produce byte-identical reports except `totals.wall_ms`.
6. Flaky/pass/fail classification matches Section 7 exactly.
7. Compare implements regression, cost delta, and warnings per Section 9.
8. No crash reaches the user (Section 11 fully covered), including: model binary timeout (30s), invalid `--runs` value, and strict-type `json_field_equals` comparisons.
9. `python -m unittest` passes from a fresh clone.
10. `prompts/classify_v2.txt` measurably outperforms `classify_v1.txt`, evidenced by real report output.
11. `IMPROVEMENT.md`, `USAGE.md`, `CLAUDE.md`, `PROMPTS.md`, `JOURNAL.md` all present.
12. First commit is spec-only, verified by `git log --reverse --stat`.

Nothing outside this document is an open question — this file is complete and self-contained. Do not add an "addendum" reconstructing missing pieces; everything needed is already above.
