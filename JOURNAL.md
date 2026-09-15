# JOURNAL.md — development log

## 2026-09-15

### 1. Spec-only initial commit (SPEC 14)

`promptlab-v1` was built fresh in a new directory (an older `promptlab/`
directory in the workspace belongs to a previous session against a different,
403-line spec variant with addendum commits; it was left untouched). The new
SPEC.md was transcribed byte-identically from the source specification
(verified with `diff` — "SPEC IDENTICAL") and committed alone:

```
$ git log --reverse --stat --oneline | head -3
ae6724e Add SPEC.md (spec-only initial commit, zero code)
 SPEC.md | 302 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 302 insertions(+++)
```

No design changes were needed afterwards — the spec is FINAL and complete, so
there are no spec-amendment commits (SPEC 14's "design changes go to SPEC.md
first" rule is vacuously satisfied).

### 2. Implementation (commit 2)

- `promptlab.py`: single-file harness — CLI with argparse mapped to exit code 1
  on usage errors; suite loading/validation (all SPEC 4 violations exit 1 with
  a message naming the field/problem; `matches` regexes compiled at load
  time so an invalid pattern fails before any model call); the eight assertion
  evaluators behind a registry dict (doctor's "assertions" check verifies it);
  the shared `extract_json()` fence-stripping helper; subprocess-only model
  invocation with the exact SPEC 2 flags, the env→cwd→suite-dir binary
  resolution, `.py`-via-`sys.executable` handling, and the locked 30-second
  timeout with message `model binary did not respond within 30s`; report
  building in fixed key order; compare; doctor.
- `stubmodel.py`: the model binary implementing the SPEC 2 CLI exactly. It is
  an instruction-following classifier stub — deterministic at temperature 0,
  seeded-random format/category degradation at temperature > 0 (reproducible
  with `--seed`/`--call-index`, OS-entropy without), token accounting via
  `ceil(len/4)`, truncation with `finish: "length"`, exit codes 0/2/3.
- `test_promptlab.py`: 80 tests (unit: helpers, all eight assertions, strict
  `json_field_equals` typing, flaky classification; suite validation and every
  exit code; end-to-end runs incl. the SPEC 3 output-flag matrix, report key
  order, temperature-0 determinism, an alternating fake model that produces a
  genuine flaky case, flag-passthrough capture, timeout/crash/garbage model
  failures; compare classifications/warnings/pct rules; doctor; the stubmodel
  contract itself; real subprocess exit codes).

Two implementation bugs were caught by the tests and fixed during development:
`random.Random` does not accept tuple seeds (stubmodel), and a leftover broken
loop in one test. One formatting expectation in a compare test was corrected
(`+20.00%`, from the spec's `round(..., 2)`).

```
$ python -m unittest
...
----------------------------------------------------------------------
Ran 80 tests in 3.699s

OK
```

### 3. Fixtures and real runs (commit 3)

Prompts (`classify_v1.txt` naive, `classify_v2.txt` format-locked) and suites
generated with a probe of the live stubmodel for the `equals` fixture. Real
runs, all from the repo root:

```
$ python promptlab.py run --suite suites/classify_v1.json   # exit 2
suite 'classify-smoke': 6 cases, 1 passed, 5 failed, 0 flaky (runs per case: 1)
result: FAIL

$ python promptlab.py run --suite suites/classify_v2.json   # exit 0
suite 'classify-smoke': 6 cases, 6 passed, 0 failed, 0 flaky (runs per case: 1)
result: PASS

$ python promptlab.py compare --baseline <v1> --candidate <v2>   # exit 0
c001: improved (0.0 -> 1.0)
c002: unchanged (1.0 -> 1.0)
c003: improved (0.0 -> 1.0)
c004: improved (0.0 -> 1.0)
c005: improved (0.0 -> 1.0)
c006: improved (0.0 -> 1.0)
cost: tokens_in 359 -> 1034 (delta +675, +188.02%) | tokens_out 382 -> 198 (delta -184, -48.17%)
summary: 0 regressed, 5 improved, 1 unchanged, 0 new, 0 removed

$ python promptlab.py doctor   # exit 0
[PASS] python
[PASS] model
[PASS] suites
[PASS] assertions
```

SPEC 5 determinism evidence (v2 suite run twice): `wall_ms` 480 vs 524, every
other byte identical (object AND `json.dumps` equality after removing
`wall_ms`). Full reports for all four prompt iterations are pasted verbatim in
`IMPROVEMENT.md`.

Flaky demo (`suites/classify_flaky_demo.json`, temperature 0.8, unseeded —
intentionally non-deterministic), one observed execution: exit 2,
`f001: flaky (0.25)`, `f002: flaky (0.75)`, totals `0 passed, 0 failed,
2 flaky`.

### 4. Decisions worth recording

- Unreadable prompt/input files exit 4 (file I/O failure bucket) rather than 3:
  the harness itself reads the prompt file (for `prompt_hash`) and
  pre-resolves input files before any invocation, so the failure is the
  harness's own read, not a model invocation.
- Report `assertions` aggregates per assertion TYPE (SPEC 5's "one entry per
  assertion type used in that case"); when a case repeats a type, the entry
  counts runs where every assertion of that type passed.
- Interim prompt/suite files (`_iter2*`, `_iter3*`) are committed so
  IMPROVEMENT.md's middle iterations stay reproducible; the one-off suite
  generator script (`_gen_suites.py`, `_build_docs.py`) was deleted after use.

### 5. Fresh-clone verification (commit 5; docs are commit 4)

See the end of this file for the appended evidence: `git clone` of this repo
into a scratch directory, `python -m unittest` green there, `doctor` green
there, a real run there, and `git log --reverse --stat` confirming the first
commit is spec-only (SPEC 15.12).

### Deviations from spec

None. Where the spec left operational choice (e.g. the exit-4 mapping above),
this file records the decision and its rationale.

---

## Appendix — fresh-clone verification evidence (2026-09-15)

Executed against a `git clone` of this repository into a scratch directory
outside the repo:

```
$ git clone <repo> scratch && cd scratch

$ python -m unittest
...
----------------------------------------------------------------------
Ran 80 tests in 4.480s

OK

$ python promptlab.py doctor
[PASS] python
[PASS] model
[PASS] suites
[PASS] assertions

$ python promptlab.py run --suite suites/classify_v2.json > /dev/null
fresh-clone run exit=0

$ git log --reverse --stat --oneline
ae6724e Add SPEC.md (spec-only initial commit, zero code)
 SPEC.md | 302 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 302 insertions(+)
373793a Implement promptlab harness, stubmodel binary, and unittest suite
 .gitignore        |   2 +
 promptlab.py      | 971 ++++++++++++++++++++++++++++++++++++++++++++++++++++++
 stubmodel.py      | 168 ++++++++++
 test_promptlab.py | 900 ++++++++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 2041 insertions(+)
f4c0533 Add prompts (classify v1/v2 + interim iterations), suites, and flaky demo
 prompts/_iter2_concise.txt      |   8 +++
 prompts/_iter3_rawjson.txt      |   8 +++
 prompts/classify_v1.txt         |   6 +++
 prompts/classify_v2.txt         |  15 ++++++
 suites/_iter2.json              | 116 ++++++++++++++++++++++++++++++++++++
 suites/_iter3.json              | 116 ++++++++++++++++++++++++++++++++++++
 suites/classify_flaky_demo.json |  24 +++++++++
 suites/classify_v1.json         | 116 ++++++++++++++++++++++++++++++++++++
 suites/classify_v2.json         | 116 ++++++++++++++++++++++++++++++++++++
 9 files changed, 525 insertions(+)
18ab6a3 Add IMPROVEMENT/USAGE/CLAUDE/PROMPTS/JOURNAL docs with real run evidence
 CLAUDE.md      |  83 +++++
 IMPROVEMENT.md | 996 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 JOURNAL.md     | 128 ++++++++
 PROMPTS.md     |  60 ++++
 USAGE.md       | 179 +++++++++++
 5 files changed, 1446 insertions(+)
```

(The `git log --reverse --stat` above predates this evidence commit; the first
commit remains spec-only — SPEC 15.12 satisfied.)

