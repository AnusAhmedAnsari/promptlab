# CLAUDE.md — guide for code agents working in this repo

## What this repo is

`promptlab` is a CLI harness that runs prompt test suites against a model
binary (`stubmodel.py`), evaluates assertions, and reports pass/fail/flaky
results and regressions between prompt versions. The specification
(`SPEC.md`) is FINAL and fully self-contained — it is the source of truth for
every contract here. When code and spec appear to disagree, fix the code.

## Map

- `promptlab.py` — the entire harness (single file): CLI (`run` / `compare` /
  `doctor`), suite loading + validation, the 8 assertion evaluators,
  subprocess model invocation, report building, compare logic, doctor checks.
- `stubmodel.py` — the model binary the harness runs. Implemented exactly per
  SPEC 2 (flags, JSON envelope, exit codes 0/2/3, `ceil(len/4)` token formula).
- `test_promptlab.py` — the unittest suite; `python -m unittest` must pass from
  a fresh clone.
- `suites/`, `prompts/` — demo fixtures (`classify_v1` baseline vs `classify_v2`
  improved; `classify_flaky_demo` intentionally non-deterministic).
- `IMPROVEMENT.md` — real-run evidence for the prompt iterations (SPEC 13).

## Locked invariants — do not break these

1. Exit codes (SPEC 3): 0 success · 1 bad usage/malformed suite · 2 any case
   failed **or flaky** (2 is a result, never a crash) · 3 model invocation
   failure · 4 file I/O failure. Never conflate 1 and 2.
2. Run output routing (SPEC 3 table): no flags → report JSON on stdout;
   `--out` → report to file, summary to stderr; `--report` → summary appended
   to stdout; `--out --report` → summary to stdout only.
3. Exactly eight assertion types (SPEC 6): contains, not_contains, equals,
   matches, json_valid, json_field_equals, max_tokens, finish_is. No new types,
   no extra CLI flags, no `--prompt-file`/`--input-file`.
4. `extract_json()` is the ONE fence-stripping helper; both JSON assertions
   call it. A fence is stripped only when it wraps the whole output.
5. `json_field_equals` uses strict Python `==` with no type coercion (`1 !=
   "1"`); a mismatch is a failed assertion, never an error.
6. All `matches` patterns are compiled at suite load time; an invalid regex
   exits 1 with zero model calls.
7. Model invocation (SPEC 2/12): subprocess only, exact flags, `--seed` /
   `--call-index` passed only when the suite's `model` object specifies them,
   binary located env-var → cwd → suite-dir, `.py` binaries via
   `sys.executable`, hard 30-second timeout with the exact message
   `model binary did not respond within 30s`.
8. Report (SPEC 5): fixed key order; `totals.cases == passed + failed + flaky`;
   tokens summed across every run of every case; per-case `assertions` has one
   entry per assertion TYPE used (first-appearance order), counts = runs where
   that type's assertions held; `failures` entries are 1-based per
   (assertion, run); `wall_ms` is the only volatile field — at temperature 0
   two runs must be byte-identical otherwise.
9. Flaky policy (SPEC 7): pass iff rate 1.0, fail iff rate 0.0, flaky
   otherwise — uniformly for any N.

10. Do not speculate about, prepare for, or add abstraction layers for any future/unknown requirement changes. Build exactly and only what SPEC.md specifies — nothing extra 'just in case.' If a new requirement arrives later, we will update SPEC.md first and then extend the code at that time — not before. Treat SPEC.md as complete and final for now.

11. `compare` (SPEC 9): any pass_rate decrease is a regression; always exits 0;
    `pct_change = round(delta/baseline*100, 2)`, `0.0` when baseline==0 and
    delta==0, else `null`.
12. Crash-proofing (SPEC 11): every failure path is a single-line stderr
    message with the right exit code — a traceback must never reach the user.

12.Do not speculate about, prepare for, or add abstraction layers for any future/unknown requirement changes. Build exactly and only what SPEC.md specifies — nothing extra 'just in case.' If a new requirement arrives later, we will update SPEC.md first and then extend the code at that time — not before. Treat SPEC.md as complete and final for now.

## Conventions

- Python 3.10+, stdlib only. Match the existing style: small functions, plain
  dicts built in schema key order, spec-section references in comments where a
  constraint is locked.
- All program output is ASCII (Windows-console safe).

## Common tasks

- Run the tests: `python -m unittest` (from the repo root).
- Try the harness: `python promptlab.py run --suite suites/classify_v2.json --report`.
- Add a suite: JSON per SPEC 4; paths are suite-file-relative.
- Iterate a prompt: copy the suite, change `prompt_file`, run both, `compare`
  the reports, and record real output in `IMPROVEMENT.md` (SPEC 13 — no
  invented numbers; at least one recorded iteration must be one that did not
  help).
- Swap the model: point `PROMPTLAB_MODEL_BIN` at any binary implementing the
  SPEC 2 CLI; do not touch the harness.

## Git discipline (SPEC 14)

The first commit contains `SPEC.md` only — verify with
`git log --reverse --stat`. Any design change must be committed to `SPEC.md`
before the corresponding code change. Do not rewrite published history.
