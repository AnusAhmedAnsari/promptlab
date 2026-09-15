#!/usr/bin/env python3
"""promptlab — CLI harness that runs prompt test suites against a model binary,
evaluates assertions on the output, and reports pass/fail/flaky results and
regressions between prompt versions.

Every contract implemented here is locked by SPEC.md (FINAL for v1):

- model binary CLI, location order, 30s subprocess timeout ... SPEC 2
- promptlab CLI surface, exit codes 0/1/2/3/4, run output table . SPEC 3
- suite format, validation, path resolution, runs validation ... SPEC 4
- report schema, prompt_hash, determinism rule, token formula . SPEC 5
- the exact eight assertion types, shared extract_json ....... SPEC 6
- flaky policy ............................................... SPEC 7
- failures detail shape ...................................... SPEC 8
- compare classification, cost delta, warnings, output ....... SPEC 9
- doctor checks and output ................................... SPEC 10
- crash-proofing (single-line stderr, no tracebacks) ......... SPEC 11
- model invoked via subprocess only .......................... SPEC 12
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

VERSION = "1.0.0"

# SPEC 2 (locked): every model invocation gets a 30-second timeout.
MODEL_TIMEOUT_SECONDS = 30

# SPEC 3: exit codes.
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_CASES_FAILED = 2
EXIT_MODEL = 3
EXIT_IO = 4

# SPEC 6: the exact eight assertion types — no substitutes.
ASSERTION_TYPES = (
    "contains",
    "not_contains",
    "equals",
    "matches",
    "json_valid",
    "json_field_equals",
    "max_tokens",
    "finish_is",
)
ASSERTION_REQUIRED_FIELDS = {
    "contains": ("value",),
    "not_contains": ("value",),
    "equals": ("value",),
    "matches": ("pattern",),
    "json_valid": (),
    "json_field_equals": ("field", "value"),
    "max_tokens": ("value",),
    "finish_is": ("value",),
}


class PromptLabError(Exception):
    """A controlled failure carrying a spec exit code and a one-line message."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def truncate_200(value) -> str:
    """SPEC 8: failure 'actual' is the first 200 chars, '...' appended if longer."""
    text = value if isinstance(value, str) else str(value)
    if len(text) > 200:
        return text[:200] + "..."
    return text


def normalize_ws(value) -> str:
    """SPEC 6 'equals' + normalize: strip and collapse whitespace."""
    return " ".join(str(value).split())


_FENCED_BLOCK_RE = re.compile(
    r"^\s*```[ \t]*\w*[ \t]*\r?\n(.*?)\r?\n[ \t]*```\s*$", re.DOTALL
)


def extract_json(text):
    """SPEC 6 (locked): the ONE shared fence-stripping + json.loads helper.

    Strips a Markdown code fence (opening ``` or ```json line plus closing ```)
    when the whole text is a fenced block, else uses the raw text; then attempts
    json.loads. Returns the parsed value, or None when parsing fails.
    json_valid and json_field_equals both go through this helper.
    """
    match = _FENCED_BLOCK_RE.match(text)
    candidate = match.group(1) if match else text
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        return None


def resolve_dotted_path(value, dotted: str):
    """Resolve 'meta.priority' style paths into parsed JSON.

    Walks dict keys and list indices. Returns (resolved_value, found);
    found is False when any path segment is missing — a failed lookup, not an error.
    """
    current = value
    for part in dotted.split("."):
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None, False
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return None, False
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return None, False
        else:
            return None, False
    return current, True


def classify_status(pass_rate: float) -> str:
    """SPEC 7 (locked): pass iff rate==1.0, fail iff rate==0.0, flaky otherwise."""
    if pass_rate == 1.0:
        return "pass"
    if pass_rate == 0.0:
        return "fail"
    return "flaky"


# ---------------------------------------------------------------------------
# Assertion evaluation (SPEC 6)
# ---------------------------------------------------------------------------
# Each handler returns (passed, expected, actual, message); the caller builds
# the SPEC 8 failure entry from the last three when the assertion failed.

def _eval_contains(assertion, output, model_data):
    value = assertion["value"]
    needle, hay = str(value), output
    if assertion.get("ignore_case"):
        needle, hay = needle.lower(), hay.lower()
    passed = needle in hay
    message = "" if passed else f"output does not contain {value!r}"
    return passed, value, truncate_200(output), message


def _eval_not_contains(assertion, output, model_data):
    value = assertion["value"]
    needle, hay = str(value), output
    if assertion.get("ignore_case"):
        needle, hay = needle.lower(), hay.lower()
    passed = needle not in hay
    message = "" if passed else f"output contains forbidden {value!r}"
    return passed, value, truncate_200(output), message


def _eval_equals(assertion, output, model_data):
    value = assertion["value"]
    if assertion.get("normalize"):
        passed = normalize_ws(output) == normalize_ws(value)
        note = " (after whitespace normalization)"
    else:
        passed = output == value
        note = ""
    message = "" if passed else f"output does not equal expected value{note}"
    return passed, value, truncate_200(output), message


def _eval_matches(assertion, output, model_data):
    pattern = assertion["pattern"]
    compiled = assertion.get("_pattern") or re.compile(pattern)
    passed = compiled.search(output) is not None
    message = "" if passed else f"output does not match pattern {pattern!r}"
    return passed, pattern, truncate_200(output), message


def _eval_json_valid(assertion, output, model_data):
    passed = extract_json(output) is not None
    message = "" if passed else "output is not valid JSON (after fence stripping)"
    return passed, None, truncate_200(output), message


def _eval_json_field_equals(assertion, output, model_data):
    field, value = assertion["field"], assertion["value"]
    parsed = extract_json(output)
    if parsed is None:
        return (
            False,
            value,
            truncate_200(output),
            "output is not valid JSON; cannot resolve field",
        )
    resolved, found = resolve_dotted_path(parsed, field)
    if not found:
        return False, value, None, f"field {field!r} not found in parsed JSON output"
    # SPEC 6 (locked): strict Python ==, no type coercion (1 != "1").
    passed = resolved == value
    if passed:
        message = ""
    elif type(resolved) is not type(value):
        message = (
            f"field {field!r} resolved to {resolved!r} ({type(resolved).__name__}), "
            f"expected {value!r} ({type(value).__name__}); strict comparison, no coercion"
        )
    else:
        message = f"field {field!r} resolved to {resolved!r}, expected {value!r}"
    return passed, value, truncate_200(resolved), message


def _eval_max_tokens(assertion, output, model_data):
    limit = assertion["value"]
    tokens_out = model_data.get("tokens_out")
    if not isinstance(tokens_out, (int, float)):
        return False, limit, tokens_out, "model did not report a numeric tokens_out"
    passed = tokens_out <= limit
    message = "" if passed else f"tokens_out {tokens_out} exceeds maximum {limit}"
    return passed, limit, tokens_out, message


def _eval_finish_is(assertion, output, model_data):
    expected = assertion["value"]
    finish = model_data.get("finish")
    passed = finish == expected
    message = "" if passed else f"finish reason is {finish!r}, expected {expected!r}"
    return passed, expected, finish, message


# The registry doctor's 'assertions' check verifies (SPEC 10).
ASSERTION_EVALUATORS = {
    "contains": _eval_contains,
    "not_contains": _eval_not_contains,
    "equals": _eval_equals,
    "matches": _eval_matches,
    "json_valid": _eval_json_valid,
    "json_field_equals": _eval_json_field_equals,
    "max_tokens": _eval_max_tokens,
    "finish_is": _eval_finish_is,
}


def evaluate_assertion(assertion, output, model_data):
    """Evaluate one assertion against one run. Returns (passed, expected, actual, message)."""
    handler = ASSERTION_EVALUATORS.get(assertion["type"])
    if handler is None:
        raise PromptLabError(
            EXIT_USAGE, f"unknown assertion type {assertion['type']!r}"
        )
    return handler(assertion, output, model_data)


# ---------------------------------------------------------------------------
# Suite loading and validation (SPEC 4)
# ---------------------------------------------------------------------------

def load_suite(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise PromptLabError(
            EXIT_IO, f"could not read suite file '{path}': {exc.strerror or exc}"
        )
    except UnicodeDecodeError as exc:
        raise PromptLabError(EXIT_IO, f"could not decode suite file '{path}': {exc}")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PromptLabError(EXIT_USAGE, f"malformed suite JSON in '{path}': {exc}")
    _validate_suite(data, path)
    return data


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_suite(data, path: str) -> None:
    where = f"suite '{path}'"

    if not isinstance(data, dict):
        raise PromptLabError(EXIT_USAGE, f"{where}: top level must be a JSON object")
    for field in ("name", "prompt_file", "cases"):
        if field not in data:
            raise PromptLabError(EXIT_USAGE, f"{where}: missing required field '{field}'")
    if not isinstance(data["name"], str) or not data["name"]:
        raise PromptLabError(EXIT_USAGE, f"{where}: field 'name' must be a non-empty string")
    if not isinstance(data["prompt_file"], str):
        raise PromptLabError(EXIT_USAGE, f"{where}: field 'prompt_file' must be a string")
    if "runs" in data and (not _is_int(data["runs"]) or data["runs"] < 1):
        raise PromptLabError(
            EXIT_USAGE,
            f"{where}: field 'runs' has invalid value {data['runs']!r}; must be a positive integer (>= 1)",
        )
    if "model" in data:
        model = data["model"]
        if not isinstance(model, dict):
            raise PromptLabError(EXIT_USAGE, f"{where}: field 'model' must be an object")
        if "temperature" in model and (
            isinstance(model["temperature"], bool)
            or not isinstance(model["temperature"], (int, float))
        ):
            raise PromptLabError(EXIT_USAGE, f"{where}: model.temperature must be a number")
        if "max_tokens" in model and not _is_int(model["max_tokens"]):
            raise PromptLabError(EXIT_USAGE, f"{where}: model.max_tokens must be an integer")
        for key in ("seed", "call_index"):
            if key in model and not _is_int(model[key]):
                raise PromptLabError(EXIT_USAGE, f"{where}: model.{key} must be an integer")

    if not isinstance(data["cases"], list):
        raise PromptLabError(EXIT_USAGE, f"{where}: field 'cases' must be a list")

    seen_ids = set()
    for index, case in enumerate(data["cases"]):
        if not isinstance(case, dict):
            raise PromptLabError(EXIT_USAGE, f"{where}: case {index} must be an object")
        for field in ("id", "input", "assert"):
            if field not in case:
                raise PromptLabError(
                    EXIT_USAGE, f"{where}: case {index} is missing required field '{field}'"
                )
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            raise PromptLabError(
                EXIT_USAGE, f"{where}: case {index} field 'id' must be a non-empty string"
            )
        if case_id in seen_ids:
            raise PromptLabError(EXIT_USAGE, f"{where}: duplicate case id '{case_id}'")
        seen_ids.add(case_id)

        spec = case["input"]
        if not isinstance(spec, (str, dict)):
            raise PromptLabError(
                EXIT_USAGE,
                f"{where}: case '{case_id}' input must be a string or an object with a 'file' key",
            )
        if isinstance(spec, dict):
            if "file" not in spec or not isinstance(spec["file"], str):
                raise PromptLabError(
                    EXIT_USAGE,
                    f"{where}: case '{case_id}' input object must have a string 'file' key",
                )

        if not isinstance(case["assert"], list):
            raise PromptLabError(
                EXIT_USAGE, f"{where}: case '{case_id}' field 'assert' must be a list"
            )
        for j_index, assertion in enumerate(case["assert"]):
            if not isinstance(assertion, dict):
                raise PromptLabError(
                    EXIT_USAGE, f"{where}: case '{case_id}' assertion {j_index} must be an object"
                )
            a_type = assertion.get("type")
            if a_type not in ASSERTION_TYPES:
                raise PromptLabError(
                    EXIT_USAGE,
                    f"{where}: case '{case_id}' assertion {j_index} has unknown type "
                    f"{a_type!r} (expected one of: {', '.join(ASSERTION_TYPES)})",
                )
            for field in ASSERTION_REQUIRED_FIELDS[a_type]:
                if field not in assertion:
                    raise PromptLabError(
                        EXIT_USAGE,
                        f"{where}: case '{case_id}' assertion {j_index} of type "
                        f"'{a_type}' is missing required field '{field}'",
                    )
            # SPEC 6 (locked): compile every 'matches' pattern at load time —
            # invalid regex fails the whole suite with exit 1 before any model call.
            if a_type == "matches":
                pattern = assertion["pattern"]
                if not isinstance(pattern, str):
                    raise PromptLabError(
                        EXIT_USAGE,
                        f"{where}: case '{case_id}' assertion {j_index} 'matches' "
                        "pattern must be a string",
                    )
                try:
                    assertion["_pattern"] = re.compile(pattern)
                except re.error as exc:
                    raise PromptLabError(
                        EXIT_USAGE,
                        f"{where}: case '{case_id}' assertion {j_index} 'matches' has "
                        f"invalid regex {pattern!r}: {exc}",
                    )


def effective_runs(cli_runs, suite: dict) -> int:
    """SPEC 4 (locked): CLI --runs wins over suite 'runs', default 1; must be >= 1."""
    runs = cli_runs if cli_runs is not None else suite.get("runs", 1)
    if not _is_int(runs) or runs < 1:
        raise PromptLabError(
            EXIT_USAGE,
            f"invalid run count {runs!r}: must be a positive integer (>= 1)",
        )
    return runs


def resolve_suite_path(suite_dir: str, declared: str) -> str:
    """SPEC 4: suite-relative path resolution, never relative to the cwd."""
    if os.path.isabs(declared):
        return os.path.normpath(declared)
    return os.path.normpath(os.path.join(suite_dir, declared))


# ---------------------------------------------------------------------------
# Model binary location and invocation (SPEC 2, 12)
# ---------------------------------------------------------------------------

def resolve_model_binary(suite_dir):
    """SPEC 2 (locked) location order: env var, cwd stubmodel.py, suite-dir stubmodel.py."""
    checked = []
    env_location = os.environ.get("PROMPTLAB_MODEL_BIN") or None
    if env_location:
        checked.append(("PROMPTLAB_MODEL_BIN", env_location))
        if os.path.isfile(env_location):
            return env_location
    cwd_location = os.path.join(os.getcwd(), "stubmodel.py")
    checked.append(("stubmodel.py in the current working directory", cwd_location))
    if os.path.isfile(cwd_location):
        return cwd_location
    if suite_dir:
        suite_location = os.path.join(suite_dir, "stubmodel.py")
        checked.append(("stubmodel.py in the suite file's directory", suite_location))
        if os.path.isfile(suite_location):
            return suite_location
    described = "; ".join(f"{label} -> '{location}'" for label, location in checked)
    if not env_location:
        described = "PROMPTLAB_MODEL_BIN (unset); " + described
    raise PromptLabError(
        EXIT_MODEL,
        f"model binary not found; checked: {described}",
    )


def invoke_model(binary_path, prompt_path, input_value, temperature,
                 max_tokens, seed=None, call_index=None) -> dict:
    """SPEC 2/12: subprocess-only invocation with the exact flags and 30s timeout."""
    if str(binary_path).endswith(".py"):
        command = [sys.executable, binary_path]
    else:
        command = [binary_path]
    command += [
        "--prompt", str(prompt_path),
        "--input", input_value,
        "--temperature", str(float(temperature)),
        "--max-tokens", str(int(max_tokens)),
    ]
    if seed is not None:
        command += ["--seed", str(int(seed))]
    if call_index is not None:
        command += ["--call-index", str(int(call_index))]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=MODEL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # subprocess.run already killed the child; SPEC 2 locks this message.
        raise PromptLabError(EXIT_MODEL, "model binary did not respond within 30s")
    except OSError as exc:
        raise PromptLabError(
            EXIT_MODEL,
            f"could not execute model binary '{binary_path}': {exc.strerror or exc}",
        )
    if proc.returncode != 0:
        stderr_lines = (proc.stderr or "").strip().splitlines()
        detail = stderr_lines[0] if stderr_lines else f"exit code {proc.returncode}"
        raise PromptLabError(
            EXIT_MODEL,
            f"model binary failed (exit code {proc.returncode}): {detail}",
        )
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise PromptLabError(
            EXIT_MODEL, "model binary output could not be parsed as JSON"
        )
    if not isinstance(data, dict) or not isinstance(data.get("output"), str):
        raise PromptLabError(
            EXIT_MODEL,
            "model binary output must be a JSON object with a string 'output' field",
        )
    return data


# ---------------------------------------------------------------------------
# run (SPEC 3, 5, 6, 7, 8)
# ---------------------------------------------------------------------------

def run_suite(suite_path: str, cli_runs) -> dict:
    suite = load_suite(suite_path)
    # SPEC 4 (locked): validate the run count before any model invocation.
    runs = effective_runs(cli_runs, suite)
    suite_dir = os.path.dirname(os.path.abspath(suite_path))

    prompt_declared = suite["prompt_file"]
    prompt_path = resolve_suite_path(suite_dir, prompt_declared)
    try:
        with open(prompt_path, "rb") as handle:
            prompt_bytes = handle.read()
    except OSError as exc:
        raise PromptLabError(
            EXIT_IO,
            f"could not read prompt file '{prompt_path}' (suite declares "
            f"'{prompt_declared}'): {exc.strerror or exc}",
        )
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()[:12]

    model_cfg = suite.get("model") or {}
    temperature = float(model_cfg.get("temperature", 0.0))
    max_tokens = int(model_cfg.get("max_tokens", 256))
    seed = model_cfg.get("seed")
    call_index = model_cfg.get("call_index")

    # Resolve every input up front so a missing file fails before any model call.
    input_values = []
    for case in suite["cases"]:
        spec = case["input"]
        if isinstance(spec, str):
            input_values.append(spec)
        else:
            file_path = resolve_suite_path(suite_dir, spec["file"])
            if not os.path.isfile(file_path):
                raise PromptLabError(
                    EXIT_IO,
                    f"input file '{file_path}' for case '{case['id']}' does not exist",
                )
            # SPEC 2: file inputs are passed as --input @<resolved_absolute_path>.
            input_values.append("@" + os.path.abspath(file_path))

    binary = resolve_model_binary(suite_dir)

    wall_start = time.perf_counter()
    totals = {
        "cases": len(suite["cases"]),
        "passed": 0,
        "failed": 0,
        "flaky": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "wall_ms": 0,
    }
    case_reports = []
    for case, input_value in zip(suite["cases"], input_values):
        case_reports.append(
            _run_case(
                case, input_value, runs, binary, prompt_path,
                temperature, max_tokens, seed, call_index, totals,
            )
        )
    totals["wall_ms"] = int(round((time.perf_counter() - wall_start) * 1000))

    return {
        "suite": suite["name"],
        "prompt_file": prompt_declared,
        "prompt_hash": prompt_hash,
        "runs": runs,
        "model": {"temperature": temperature, "max_tokens": max_tokens},
        "totals": totals,
        "cases": case_reports,
    }


def _run_case(case, input_value, runs, binary, prompt_path, temperature,
              max_tokens, seed, call_index, totals) -> dict:
    assertions = case["assert"]
    # SPEC 5: one assertions-report entry per assertion TYPE used in this case
    # (first-appearance order); a type's entry counts runs where its assertions held.
    type_order = []
    for assertion in assertions:
        if assertion["type"] not in type_order:
            type_order.append(assertion["type"])
    type_all_pass_by_run = {t: [True] * runs for t in type_order}

    failures = []
    passed_runs = 0
    tokens_out_sum = 0
    for run_index in range(1, runs + 1):
        data = invoke_model(
            binary, prompt_path, input_value, temperature, max_tokens,
            seed, call_index,
        )
        totals["tokens_in"] += int(data.get("tokens_in") or 0)
        totals["tokens_out"] += int(data.get("tokens_out") or 0)
        tokens_out_sum += int(data.get("tokens_out") or 0)
        output = data["output"]

        run_all_ok = True
        for assertion in assertions:
            passed, expected, actual, message = evaluate_assertion(assertion, output, data)
            if passed:
                continue
            run_all_ok = False
            type_all_pass_by_run[assertion["type"]][run_index - 1] = False
            failures.append({
                "run_index": run_index,
                "assertion_type": assertion["type"],
                "expected": expected,
                "actual": actual,
                "message": message,
            })
        if run_all_ok:
            passed_runs += 1

    pass_rate = passed_runs / runs
    status = classify_status(pass_rate)
    totals[{"pass": "passed", "fail": "failed", "flaky": "flaky"}[status]] += 1

    assertion_stats = []
    for a_type in type_order:
        type_passed = sum(type_all_pass_by_run[a_type])
        assertion_stats.append({
            "type": a_type,
            "passed": type_passed,
            "failed": runs - type_passed,
        })

    average = tokens_out_sum / runs
    tokens_out_avg = int(average) if average == int(average) else average

    return {
        "id": case["id"],
        "status": status,
        "pass_rate": pass_rate,
        "tokens_out_avg": tokens_out_avg,
        "assertions": assertion_stats,
        "failures": failures,
    }


def human_summary(report: dict) -> str:
    totals = report["totals"]
    verdict = "PASS" if totals["failed"] == 0 and totals["flaky"] == 0 else "FAIL"
    return (
        f"suite '{report['suite']}': {totals['cases']} cases, "
        f"{totals['passed']} passed, {totals['failed']} failed, "
        f"{totals['flaky']} flaky (runs per case: {report['runs']})\n"
        f"tokens_in={totals['tokens_in']} tokens_out={totals['tokens_out']} "
        f"wall_ms={totals['wall_ms']}\n"
        f"result: {verdict}"
    )


def cmd_run(args) -> int:
    report = run_suite(args.suite, args.runs)
    exit_code = (
        EXIT_OK
        if report["totals"]["failed"] == 0 and report["totals"]["flaky"] == 0
        else EXIT_CASES_FAILED
    )
    summary = human_summary(report)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(report, indent=2) + "\n")
        except OSError as exc:
            raise PromptLabError(
                EXIT_IO, f"could not write report file '{args.out}': {exc.strerror or exc}"
            )
        # SPEC 3 output table: with --out the human summary goes to stderr,
        # unless --report also moves it to stdout.
        if args.report:
            print(summary)
        else:
            print(summary, file=sys.stderr)
    else:
        print(json.dumps(report, indent=2))
        if args.report:
            print(summary)
    return exit_code


# ---------------------------------------------------------------------------
# compare (SPEC 9)
# ---------------------------------------------------------------------------

def load_report(path: str, role: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise PromptLabError(
            EXIT_IO,
            f"could not read {role} report file '{path}': {exc.strerror or exc}",
        )
    except UnicodeDecodeError as exc:
        raise PromptLabError(EXIT_IO, f"could not decode {role} report file '{path}': {exc}")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PromptLabError(
            EXIT_USAGE, f"malformed JSON in {role} report '{path}': {exc}"
        )
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("totals"), dict)
        or not isinstance(data.get("cases"), list)
    ):
        raise PromptLabError(
            EXIT_USAGE,
            f"{role} report '{path}' is missing the required 'totals'/'cases' structure",
        )
    for key in ("tokens_in", "tokens_out"):
        if not isinstance(data["totals"].get(key), (int, float)):
            raise PromptLabError(
                EXIT_USAGE,
                f"{role} report '{path}' totals is missing numeric '{key}'",
            )
    for index, case in enumerate(data["cases"]):
        if not isinstance(case, dict) or "id" not in case or "pass_rate" not in case:
            raise PromptLabError(
                EXIT_USAGE,
                f"{role} report '{path}': case entry {index} is missing 'id' or 'pass_rate'",
            )
    return data


def compare_warnings(baseline: dict, candidate: dict) -> list:
    warnings = []
    base_hash, cand_hash = baseline.get("prompt_hash"), candidate.get("prompt_hash")
    if base_hash and cand_hash and base_hash == cand_hash:
        warnings.append(
            f"baseline and candidate share the same prompt_hash ({base_hash})"
        )
    if baseline.get("suite") != candidate.get("suite"):
        warnings.append(
            f"suite names differ: baseline '{baseline.get('suite')}' vs "
            f"candidate '{candidate.get('suite')}'"
        )
    if baseline.get("model") != candidate.get("model"):
        warnings.append(
            "model settings differ: baseline "
            f"{json.dumps(baseline.get('model'), sort_keys=True)} vs candidate "
            f"{json.dumps(candidate.get('model'), sort_keys=True)}"
        )
    return warnings


def _format_rate(rate) -> str:
    return "n/a" if rate is None else str(rate)


def _format_cost_part(name: str, entry: dict) -> str:
    pct = entry["pct_change"]
    pct_text = "n/a" if pct is None else f"{pct:+.2f}%"
    return (
        f"{name} {entry['baseline']} -> {entry['candidate']} "
        f"(delta {entry['delta']:+d}, {pct_text})"
    )


def cmd_compare(args) -> int:
    baseline = load_report(args.baseline, "baseline")
    candidate = load_report(args.candidate, "candidate")
    warnings = compare_warnings(baseline, candidate)

    base_rates = {c["id"]: c["pass_rate"] for c in baseline["cases"]}
    cand_rates = {c["id"]: c["pass_rate"] for c in candidate["cases"]}
    ordered_ids = [c["id"] for c in baseline["cases"]]
    ordered_ids += [c["id"] for c in candidate["cases"] if c["id"] not in base_rates]

    case_results = {}
    counts = {"regressed": 0, "improved": 0, "unchanged": 0, "new": 0, "removed": 0}
    for case_id in ordered_ids:
        base_rate = base_rates.get(case_id)
        cand_rate = cand_rates.get(case_id)
        if base_rate is None:
            classification = "new"
        elif cand_rate is None:
            classification = "removed"
        elif cand_rate < base_rate:
            classification = "regressed"
        elif cand_rate > base_rate:
            classification = "improved"
        else:
            classification = "unchanged"
        counts[classification] += 1
        case_results[case_id] = {
            "classification": classification,
            "baseline_pass_rate": base_rate,
            "candidate_pass_rate": cand_rate,
        }

    cost = {}
    for key in ("tokens_in", "tokens_out"):
        base_value = int(baseline["totals"][key])
        cand_value = int(candidate["totals"][key])
        delta = cand_value - base_value
        if base_value != 0:
            pct_change = round(delta / base_value * 100, 2)
        else:
            pct_change = 0.0 if delta == 0 else None
        cost[key] = {
            "baseline": base_value,
            "candidate": cand_value,
            "delta": delta,
            "pct_change": pct_change,
        }

    for warning in warnings:
        print(f"WARNING: {warning}")
    for case_id, result in case_results.items():
        print(
            f"{case_id}: {result['classification']} "
            f"({_format_rate(result['baseline_pass_rate'])} -> "
            f"{_format_rate(result['candidate_pass_rate'])})"
        )
    print(
        "cost: "
        + " | ".join(_format_cost_part(k, cost[k]) for k in ("tokens_in", "tokens_out"))
    )
    print(
        f"summary: {counts['regressed']} regressed, {counts['improved']} improved, "
        f"{counts['unchanged']} unchanged, {counts['new']} new, {counts['removed']} removed"
    )

    if args.out:
        diff = {
            "baseline": args.baseline,
            "candidate": args.candidate,
            "warnings": warnings,
            "cost": cost,
            "cases": case_results,
            "summary": counts,
        }
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(diff, indent=2) + "\n")
        except OSError as exc:
            raise PromptLabError(
                EXIT_IO, f"could not write diff file '{args.out}': {exc.strerror or exc}"
            )
    return EXIT_OK


# ---------------------------------------------------------------------------
# doctor (SPEC 10)
# ---------------------------------------------------------------------------

def _doctor_python() -> bool:
    return sys.version_info >= (3, 10)


def _doctor_model() -> bool:
    try:
        binary = resolve_model_binary(None)
        fd, prompt_path = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("Classify the user message.\n")
            data = invoke_model(binary, prompt_path, "hello world", 0.0, 64)
            return isinstance(data.get("output"), str)
        finally:
            os.unlink(prompt_path)
    except PromptLabError:
        return False


def _doctor_suites() -> bool:
    found = []
    if os.path.isdir("suites"):
        found += glob.glob(os.path.join("suites", "*.json"))
    found += glob.glob("*.json")
    return bool(found)


def _doctor_assertions() -> bool:
    expected = set(ASSERTION_TYPES)
    registered = set(ASSERTION_EVALUATORS)
    return expected == registered and all(
        callable(ASSERTION_EVALUATORS[a_type]) for a_type in ASSERTION_TYPES
    )


def cmd_doctor(args) -> int:
    checks = (
        ("python", _doctor_python),
        ("model", _doctor_model),
        ("suites", _doctor_suites),
        ("assertions", _doctor_assertions),
    )
    for name, check in checks:
        print(f"[{'PASS' if check() else 'FAIL'}] {name}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI plumbing (SPEC 3, 11)
# ---------------------------------------------------------------------------

class _SpecParser(argparse.ArgumentParser):
    """argparse that maps usage errors onto SPEC 3's exit code 1."""

    def error(self, message):
        raise PromptLabError(EXIT_USAGE, f"bad usage: {message}")


def build_parser() -> _SpecParser:
    parser = _SpecParser(
        prog="promptlab",
        description="promptlab - prompt test harness (contracts locked by SPEC.md)",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command", required=True)

    run_parser = subparsers.add_parser("run", help="run a prompt test suite")
    run_parser.add_argument("--suite", required=True, help="path to the suite JSON file")
    run_parser.add_argument("--runs", type=int, default=None,
                            help="override the suite's run count (default: suite value or 1)")
    run_parser.add_argument("--out", default=None,
                            help="write the report JSON to this file instead of stdout")
    run_parser.add_argument("--report", action="store_true",
                            help="also print the human summary")
    run_parser.set_defaults(func=cmd_run)

    compare_parser = subparsers.add_parser(
        "compare", help="compare two run reports"
    )
    compare_parser.add_argument("--baseline", required=True, help="baseline report JSON")
    compare_parser.add_argument("--candidate", required=True, help="candidate report JSON")
    compare_parser.add_argument("--out", default=None, help="also write the diff JSON here")
    compare_parser.set_defaults(func=cmd_compare)

    doctor_parser = subparsers.add_parser("doctor", help="environment self-check")
    doctor_parser.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        return args.func(args)
    except PromptLabError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # SPEC 11: no traceback ever reaches the user.
        print(
            f"promptlab: internal error: {type(exc).__name__}: {exc}", file=sys.stderr
        )
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
