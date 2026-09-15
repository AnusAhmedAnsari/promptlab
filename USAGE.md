# USAGE.md — how to use promptlab

`promptlab` runs prompt test suites against a model binary, evaluates the eight
spec'd assertion types on every run of every case, and reports pass/fail/flaky
results plus regression comparisons between prompt versions. All contracts are
locked in `SPEC.md`; this file is the operator's manual.

## Requirements

- Python 3.10+ (stdlib only — no third-party dependencies)
- `stubmodel.py` (in this repo) or any swap-in binary implementing the Section 2
  model contract

## Quickstart

```
$ python promptlab.py doctor
[PASS] python
[PASS] model
[PASS] suites
[PASS] assertions

$ python promptlab.py run --suite suites/classify_v1.json --report   # exit 2 (5 failed)
$ python promptlab.py run --suite suites/classify_v2.json --report   # exit 0 (6 passed)

$ python promptlab.py run --suite suites/classify_v1.json --out v1.json
$ python promptlab.py run --suite suites/classify_v2.json --out v2.json
$ python promptlab.py compare --baseline v1.json --candidate v2.json
```

`python -m promptlab ...` (from the repo root) is equivalent to
`python promptlab.py ...`.

## Commands

### `run`

```
promptlab run --suite <file> [--runs N] [--out report.json] [--report]
```

- `--suite` (required): path to the suite JSON.
- `--runs N`: overrides the suite's `runs` field (default: suite value, else 1).
  The effective count must be a positive integer — `0`, negatives, and
  non-integers exit 1 before any model call.
- `--out FILE`: write the report JSON to FILE.
- `--report`: also print the short human summary.

Output routing is locked by SPEC 3:

| Flags | stdout | stderr | file |
|---|---|---|---|
| (none) | full report JSON | — | — |
| `--out FILE` | — | short human summary | report JSON → FILE |
| `--report` | report JSON + human summary | — | — |
| `--out FILE --report` | human summary | — | report JSON → FILE |

Exit code: 0 all passed · 2 any case failed **or flaky** · 1 bad usage/malformed
suite · 3 model invocation failure · 4 file I/O failure.

### `compare`

```
promptlab compare --baseline <report.json> --candidate <report.json> [--out diff.json]
```

Prints warnings first (`WARNING: ...` lines for identical `prompt_hash`,
differing suite names, differing model settings), then one line per case
(`<id>: <classification> (baseline -> candidate)`, `n/a` for new/removed sides),
then a cost-delta line, then a summary count line. With `--out`, writes the
diff JSON (classification, rates, token cost with `pct_change`, warnings,
summary). `compare` always exits 0 when it completes — regressions are results,
not crashes.

### `doctor`

Prints four lines, in order, and always exits 0:

```
[PASS|FAIL] python      # interpreter is 3.10+
[PASS|FAIL] model       # located binary answers a minimal real invocation with valid JSON
[PASS|FAIL] suites      # at least one *.json under ./suites/ (if it exists) or in the cwd
[PASS|FAIL] assertions  # all 8 spec'd types are registered in the running code
```

## Suite format

See `suites/classify_v2.json` for a full example. Required top-level fields:
`name`, `prompt_file`, `cases`. Optional: `model` (`temperature`, `max_tokens`,
and pass-through-only `seed`/`call_index`), `runs` (positive int, default 1).

- `prompt_file` and per-case `input.file` paths resolve **relative to the suite
  file's own directory**, never the cwd. File inputs are passed to the model as
  `--input @<resolved_absolute_path>`.
- Each case needs a unique non-empty `id`, an `input` (string or
  `{"file": "path"}`), and an `assert` list (an empty list auto-passes).
- Every assertion is evaluated on every run; a run passes only if all of a
  case's assertions pass on that run.

### The eight assertion types (no others exist)

| Type | Fields | Passes when |
|---|---|---|
| `contains` | `value`, optional `ignore_case` | output contains `value` |
| `not_contains` | `value`, optional `ignore_case` | output does not contain `value` |
| `equals` | `value`, optional `normalize` | output equals `value` (normalize strips/collapses whitespace) |
| `matches` | `pattern` | `re.search(pattern, output)` matches (compiled at suite load) |
| `json_valid` | — | output parses as JSON after fence stripping |
| `json_field_equals` | `field`, `value` | dotted path resolves to `value` under strict `==` (no coercion: `1 != "1"`) |
| `max_tokens` | `value` | model-reported `tokens_out <= value` |
| `finish_is` | `value` | model-reported `finish == value` |

The fenced-JSON rule: a whole-output Markdown fence (``` / ```json) is stripped
before `json.loads`; chatty prose around a fence is NOT extracted. Both JSON
assertions share one helper.

## Report schema (temperature-0 deterministic)

Top-level keys in fixed order: `suite`, `prompt_file`, `prompt_hash` (first 12
hex chars of sha256 of the prompt file bytes), `runs`, `model`, `totals`,
`cases`. `totals` counts cases by final status (`cases = passed + failed +
flaky`), sums `tokens_in`/`tokens_out` across every run, and carries the only
volatile field, `wall_ms`. Per case: `id`, `status`, `pass_rate`,
`tokens_out_avg`, one `assertions` entry per assertion type used
(`passed`/`failed` = runs where that type's assertions held), and `failures`
(one entry per failing assertion-run pair, 1-based `run_index`, `actual`
truncated to 200 chars + `...`).

At temperature 0 two runs of the same suite produce byte-identical reports
except `wall_ms`. Token formula everywhere: `tokens = ceil(len(text) / 4)`.

## The model binary

The harness never imports the model — subprocess only, with the exact flags
`--prompt`, `--input`, `--temperature`, `--max-tokens` (plus `--seed` /
`--call-index` only when the suite's `model` object specifies them), and a
mandatory 30-second timeout (a hung binary is killed and reported as exit 3:
`model binary did not respond within 30s`).

Binary resolution order: (1) `PROMPTLAB_MODEL_BIN` env var, (2)
`./stubmodel.py`, (3) `stubmodel.py` next to the suite file. `.py` binaries run
as `[sys.executable, path, ...]`; anything else runs directly. Swap in any
executable implementing the Section 2 contract by pointing
`PROMPTLAB_MODEL_BIN` at it — no harness changes needed.

`stubmodel.py` itself: deterministic at temperature 0; at temperature > 0 it
degrades format/classification via a seeded RNG (`--seed` makes it
reproducible; without `--seed`/`--call-index` it uses OS entropy, which is what
`suites/classify_flaky_demo.json` exercises — that suite is intentionally
non-deterministic and exists to demo flaky classification).

## Error messages (never a traceback)

Every failure prints one line to stderr with the right exit code, e.g.:

```
could not read suite file 'nope.json': no such file or directory        # exit 4
malformed suite JSON in 's.json': ...                                    # exit 1
suite 's.json': assertion 0 has unknown type 'min_length' (expected ...) # exit 1
invalid run count 0: must be a positive integer (>= 1)                   # exit 1
model binary not found; checked: PROMPTLAB_MODEL_BIN (unset); ...        # exit 3
model binary did not respond within 30s                                  # exit 3
could not read prompt file 'prompts/x.txt' (suite declares '...'): ...   # exit 4
```

## Repository layout

```
promptlab.py   the harness (single file: run / compare / doctor)
stubmodel.py   the stub model binary (SPEC 2 contract)
prompts/       classify_v1.txt (baseline), classify_v2.txt (improved), interim prompts
suites/        classify_v1.json, classify_v2.json, classify_flaky_demo.json
test_promptlab.py  unittest suite (python -m unittest)
SPEC.md        the locked specification
IMPROVEMENT.md prompt iteration evidence (real runs)
PROMPTS.md     prompt design notes
JOURNAL.md     development log and verification evidence
CLAUDE.md      guide for code agents working in this repo
```
