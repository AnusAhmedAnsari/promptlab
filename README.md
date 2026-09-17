# promptlab

A command-line test harness for AI prompts. Run a suite of test cases against a prompt, evaluate assertions on what comes back, and measure whether one version of a prompt is actually better than another — including flaky (non-deterministic) behavior and regressions.

Built for Module 1 Hackathon, following [`SPEC.md`](./SPEC.md) (written and committed before any implementation code).

---

## Requirements

- Python 3.10+ (no third-party packages — standard library only)
- No network access needed — everything runs locally against `stubmodel.py`

Check your Python version:
```
python --version
```

---

## Quick Start (fresh clone, under 5 minutes)

```bash
git clone https://github.com/AnusAhmedAnsari/promptlab.git
cd promptlab

# 1. Verify the environment is healthy
python promptlab.py doctor

# 2. Run the unit test suite
python -m unittest

# 3. Run a smoke suite against the improved prompt
python promptlab.py run --suite suites/classify_v2.json --report
```

If `doctor` prints four `[PASS]` lines and `run` exits with `result: PASS`, the environment is fully working.

---

## Commands

### `doctor` — environment health check

```
python promptlab.py doctor
```

Checks: Python version, model binary reachable, suite files discoverable, all 8 assertion types registered. Run this first if anything else isn't working.

### `run` — execute a test suite against a prompt

```
python promptlab.py run --suite <suite-file> [--runs N] [--out report.json] [--report]
```

| Flag | Purpose |
|---|---|
| `--suite <file>` | Required. Path to the suite JSON file |
| `--runs N` | Run each case N times (needed to detect flaky behavior above temperature 0) |
| `--out report.json` | Write the full report to a file |
| `--report` | Print a human-readable summary |

Example:
```
python promptlab.py run --suite suites/classify_v2.json --out v2_report.json --report
```

**Exit codes:** `0` all cases passed · `1` bad usage / malformed suite · `2` one or more cases failed or were flaky · `3` model binary could not be invoked · `4` a suite or report file was unreadable.

### `compare` — measure the difference between two prompt versions

```
python promptlab.py compare --baseline <report.json> --candidate <report.json> [--out diff.json]
```

Example:
```
python promptlab.py run --suite suites/classify_v1.json --out v1_report.json
python promptlab.py run --suite suites/classify_v2.json --out v2_report.json
python promptlab.py compare --baseline v1_report.json --candidate v2_report.json
```

Classifies every case as `regressed`, `improved`, `unchanged`, `new`, or `removed`, and reports the token-cost delta between the two versions.

---

## Project Structure

```
promptlab.py          the CLI harness (run / compare / doctor)
stubmodel.py           local offline stand-in for an LLM, used for testing
test_promptlab.py      unittest suite for the harness itself
prompts/
  classify_v1.txt       the original, deliberately weak prompt
  classify_v2.txt        the improved prompt
suites/
  classify_v1.json        test suite for the v1 prompt
  classify_v2.json         test suite for the v2 prompt
  classify_flaky_demo.json  suite demonstrating flaky (non-deterministic) classification
SPEC.md                the complete specification, written before any code
CLAUDE.md              context file used to drive Claude Code
PROMPTS.md             the key prompts used during development
USAGE.md               documentation for an LLM agent running this harness unattended
IMPROVEMENT.md         evidence of the v1 → v2 prompt improvement, iteration by iteration
JOURNAL.md             development log
```

---

## How Prompt Testing Works Here

Each suite defines a set of test **cases**. Each case sends an input to the model (via `stubmodel.py`, run as a subprocess — never imported) and checks the output against a list of **assertions** (`json_valid`, `contains`, `max_tokens`, etc. — 8 types total, see `SPEC.md` Section 6).

At `temperature 0`, results are deterministic — a case either **passes** or **fails**. Above temperature 0, the same case can behave differently across runs, so `--runs N` repeats each case and classifies it as:

- **pass** — passed every run
- **fail** — failed every run
- **flaky** — passed some runs, failed others (this is *not* the same as passing — see `suites/classify_flaky_demo.json` for a live example)

---

## Verifying the Prompt Improvement

The included `classify_v1.txt` (weak) vs `classify_v2.txt` (improved) prompts can be compared directly:

```
python promptlab.py run --suite suites/classify_v1.json --report
python promptlab.py run --suite suites/classify_v2.json --report
```

Full evidence across four iterations — including one change that did *not* help — is documented in [`IMPROVEMENT.md`](./IMPROVEMENT.md).

---

## Development Process

This project follows spec-driven development: [`SPEC.md`](./SPEC.md) was written and committed first, with **zero implementation code**, before any harness code was written. Verify this yourself:

```
git log --reverse --stat --oneline
```

The first commit should show only `SPEC.md`.

---

## License

Built as a hackathon submission. See individual files for details.
