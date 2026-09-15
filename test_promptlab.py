"""Tests for promptlab and stubmodel.

SPEC.md Section 15.9: `python -m unittest` must pass from a fresh clone.
All end-to-end tests build their own suites in temp directories and point
PROMPTLAB_MODEL_BIN at the repo's stubmodel.py, so nothing depends on the
repository's demo fixtures.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

import promptlab as pl  # noqa: E402

STUB_BIN = str(REPO_ROOT / "stubmodel.py")
HARNESS = str(REPO_ROOT / "promptlab.py")

STRICT_PROMPT = "Classify the message.\nRespond with raw JSON only.\n"
CHATTY_PROMPT = "Classify the message.\n"


class HarnessTestCase(unittest.TestCase):
    """Base: temp dir, model env var, cwd save/restore, in-process CLI runner."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="promptlab-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._old_env = os.environ.get("PROMPTLAB_MODEL_BIN")
        os.environ["PROMPTLAB_MODEL_BIN"] = STUB_BIN
        self.addCleanup(self._restore_model_env)
        self._old_cwd = os.getcwd()
        self.addCleanup(os.chdir, self._old_cwd)

    def _restore_model_env(self):
        if self._old_env is None:
            os.environ.pop("PROMPTLAB_MODEL_BIN", None)
        else:
            os.environ["PROMPTLAB_MODEL_BIN"] = self._old_env

    def cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pl.main(argv)
        return code, out.getvalue(), err.getvalue()

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def suite_file(self, cases, prompt_text=STRICT_PROMPT, runs=None,
                   model=None, name="suite.json"):
        self.write("prompt.txt", prompt_text)
        suite = {"name": "test-suite", "prompt_file": "prompt.txt", "cases": cases}
        if runs is not None:
            suite["runs"] = runs
        if model is not None:
            suite["model"] = model
        return self.write(name, json.dumps(suite, indent=2))

    def fake_model(self, body, name="fake_model.py"):
        return self.write(name, body)


# ---------------------------------------------------------------------------
# Unit tests: shared helpers
# ---------------------------------------------------------------------------

class ExtractJsonTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(pl.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_json_with_tag(self):
        self.assertEqual(pl.extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_fenced_bare(self):
        self.assertEqual(pl.extract_json('```\n{"a": 1}\n```'), {"a": 1})

    def test_preamble_before_fence_is_not_stripped(self):
        # Only a whole-text fence is stripped; chatty preamble + fence stays raw
        # and therefore fails to parse (SPEC 6 helper is intentionally minimal).
        self.assertIsNone(pl.extract_json('Sure!\n```json\n{"a": 1}\n```'))

    def test_garbage_returns_none(self):
        self.assertIsNone(pl.extract_json("not json at all"))
        self.assertIsNone(pl.extract_json(""))

    def test_scalar_parses(self):
        self.assertEqual(pl.extract_json("42"), 42)


class DottedPathTests(unittest.TestCase):
    def test_nested_found(self):
        self.assertEqual(pl.resolve_dotted_path({"meta": {"priority": "high"}}, "meta.priority"),
                         ("high", True))

    def test_missing_key(self):
        self.assertEqual(pl.resolve_dotted_path({"a": {}}, "a.b"), (None, False))

    def test_into_scalar(self):
        self.assertEqual(pl.resolve_dotted_path({"a": 5}, "a.b"), (None, False))

    def test_list_index(self):
        self.assertEqual(pl.resolve_dotted_path({"items": [1, 2]}, "items.1"), (2, True))

    def test_list_index_out_of_range(self):
        self.assertEqual(pl.resolve_dotted_path({"items": [1]}, "items.5"), (None, False))

    def test_non_integer_list_index(self):
        self.assertEqual(pl.resolve_dotted_path({"items": [1]}, "items.x"), (None, False))


class TruncateTests(unittest.TestCase):
    def test_at_200_chars_no_ellipsis(self):
        self.assertEqual(len(pl.truncate_200("x" * 200)), 200)

    def test_over_200_gets_ellipsis(self):
        result = pl.truncate_200("x" * 201)
        self.assertEqual(result, "x" * 200 + "...")
        self.assertEqual(len(result), 203)

    def test_non_string_stringified(self):
        self.assertEqual(pl.truncate_200(1234), "1234")


class StatusTests(unittest.TestCase):
    def test_pass_fail_flaky(self):
        self.assertEqual(pl.classify_status(1.0), "pass")
        self.assertEqual(pl.classify_status(0.0), "fail")
        self.assertEqual(pl.classify_status(0.5), "flaky")
        self.assertEqual(pl.classify_status(2 / 3), "flaky")


# ---------------------------------------------------------------------------
# Unit tests: the eight assertion types (SPEC 6)
# ---------------------------------------------------------------------------

class AssertionTests(unittest.TestCase):
    def evaluate(self, assertion, output, tokens_out=20, finish="stop"):
        return pl.evaluate_assertion(
            assertion, output,
            {"output": output, "tokens_in": 5, "tokens_out": tokens_out,
             "finish": finish, "latency_ms": 1},
        )

    def test_contains_pass_fail_ignore_case(self):
        self.assertTrue(self.evaluate({"type": "contains", "value": "hello"},
                                      "well hello there")[0])
        self.assertFalse(self.evaluate({"type": "contains", "value": "HELLO"},
                                       "well hello there")[0])
        self.assertTrue(self.evaluate(
            {"type": "contains", "value": "HELLO", "ignore_case": True},
            "well hello there")[0])

    def test_not_contains(self):
        self.assertTrue(self.evaluate({"type": "not_contains", "value": "Sure"},
                                      "plain answer")[0])
        self.assertFalse(self.evaluate({"type": "not_contains", "value": "Sure"},
                                       "Sure! here")[0])

    def test_equals_strict_and_normalized(self):
        self.assertTrue(self.evaluate({"type": "equals", "value": "abc"}, "abc")[0])
        self.assertFalse(self.evaluate({"type": "equals", "value": "abc"}, " abc ")[0])
        self.assertTrue(self.evaluate(
            {"type": "equals", "value": "a  b", "normalize": True}, "  a   b  ")[0])

    def test_matches(self):
        assertion = {"type": "matches", "pattern": r"\d+",
                     "_pattern": re.compile(r"\d+")}
        self.assertTrue(self.evaluate(assertion, "order 555 shipped")[0])
        self.assertFalse(self.evaluate(assertion, "no digits")[0])

    def test_json_valid(self):
        self.assertTrue(self.evaluate({"type": "json_valid"}, '{"a": 1}')[0])
        self.assertTrue(self.evaluate({"type": "json_valid"}, '```json\n{"a": 1}\n```')[0])
        self.assertFalse(self.evaluate({"type": "json_valid"}, "oops")[0])

    def test_json_field_equals_nested(self):
        assertion = {"type": "json_field_equals", "field": "meta.priority", "value": "high"}
        self.assertTrue(self.evaluate(assertion, '{"meta": {"priority": "high"}}')[0])

    def test_json_field_equals_strict_no_type_coercion(self):
        # SPEC 6 (locked): 1 != "1".
        number = {"type": "json_field_equals", "field": "n", "value": 1}
        as_string = {"type": "json_field_equals", "field": "n", "value": "1"}
        output = '{"n": 1}'
        self.assertTrue(self.evaluate(number, output)[0])
        self.assertFalse(self.evaluate(as_string, output)[0])

    def test_json_field_equals_missing_field_is_failure_not_error(self):
        assertion = {"type": "json_field_equals", "field": "nope", "value": 1}
        passed, expected, actual, message = self.evaluate(assertion, '{"a": 1}')
        self.assertFalse(passed)
        self.assertIsNone(actual)
        self.assertIn("not found", message)

    def test_json_field_equals_unparsable_output(self):
        assertion = {"type": "json_field_equals", "field": "a", "value": 1}
        passed, _, _, message = self.evaluate(assertion, "not json")
        self.assertFalse(passed)
        self.assertIn("not valid JSON", message)

    def test_max_tokens(self):
        assertion = {"type": "max_tokens", "value": 25}
        self.assertTrue(self.evaluate(assertion, "x", tokens_out=25)[0])
        self.assertFalse(self.evaluate(assertion, "x", tokens_out=26)[0])

    def test_finish_is(self):
        assertion = {"type": "finish_is", "value": "stop"}
        self.assertTrue(self.evaluate(assertion, "x", finish="stop")[0])
        self.assertFalse(self.evaluate(assertion, "x", finish="length")[0])

    def test_all_eight_types_registered(self):
        self.assertEqual(tuple(sorted(pl.ASSERTION_EVALUATORS)), tuple(sorted(pl.ASSERTION_TYPES)))
        self.assertEqual(len(pl.ASSERTION_TYPES), 8)


# ---------------------------------------------------------------------------
# Suite validation (SPEC 4) and exit codes (SPEC 3)
# ---------------------------------------------------------------------------

class SuiteValidationTests(HarnessTestCase):
    def raw_suite(self, text):
        return self.write("raw.json", text)

    def test_missing_suite_file_exit4(self):
        code, _, err = self.cli(["run", "--suite", str(self.tmp / "nope.json")])
        self.assertEqual(code, 4)
        self.assertIn("could not read suite file", err)

    def test_malformed_suite_json_exit1(self):
        path = self.raw_suite("{not json")
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 1)
        self.assertIn("malformed suite JSON", err)

    def test_missing_top_level_field(self):
        for missing in ("name", "prompt_file", "cases"):
            suite = {"name": "s", "prompt_file": "prompt.txt", "cases": []}
            suite.pop(missing)
            path = self.write("raw.json", json.dumps(suite))
            code, _, err = self.cli(["run", "--suite", path])
            self.assertEqual(code, 1, missing)
            self.assertIn(missing, err)

    def test_case_missing_required_field(self):
        for missing in ("id", "input", "assert"):
            case = {"id": "c1", "input": "hi", "assert": []}
            case.pop(missing)
            path = self.suite_file([case])
            code, _, err = self.cli(["run", "--suite", path])
            self.assertEqual(code, 1, missing)
            self.assertIn(missing, err)

    def test_input_wrong_type(self):
        path = self.suite_file([{"id": "c1", "input": 42, "assert": []}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 1)
        self.assertIn("input", err)

    def test_unknown_assertion_type(self):
        path = self.suite_file([{"id": "c1", "input": "hi",
                                 "assert": [{"type": "min_length", "value": 5}]}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 1)
        self.assertIn("unknown type", err)
        self.assertIn("min_length", err)

    def test_assertion_missing_required_field(self):
        path = self.suite_file([{"id": "c1", "input": "hi",
                                 "assert": [{"type": "json_field_equals", "field": "a"}]}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 1)
        self.assertIn("missing required field 'value'", err)

    def test_duplicate_case_id(self):
        case = {"id": "c1", "input": "hi", "assert": []}
        path = self.suite_file([case, dict(case)])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 1)
        self.assertIn("duplicate case id 'c1'", err)

    def test_invalid_regex_fails_before_any_model_call(self):
        log = self.tmp / "calls.log"
        os.environ["FAKE_MODEL_LOG"] = str(log)
        counting = self.fake_model(
            "import json, os\n"
            "open(os.environ['FAKE_MODEL_LOG'], 'a').write('x')\n"
            "print(json.dumps({'output': 'ok', 'tokens_in': 1, 'tokens_out': 1,"
            " 'finish': 'stop', 'latency_ms': 1}))\n"
        )
        os.environ["PROMPTLAB_MODEL_BIN"] = counting
        path = self.suite_file([
            {"id": "ok", "input": "hi", "assert": [{"type": "json_valid"}]},
            {"id": "bad", "input": "hi",
             "assert": [{"type": "matches", "pattern": "(unclosed"}]},
        ])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 1)
        self.assertIn("invalid regex", err)
        self.assertFalse(log.exists(), "model must not be invoked for an invalid suite")

    def test_invalid_runs_values_exit1(self):
        for runs_value in (0, -2, 1.5, "2"):
            suite = {"name": "s", "prompt_file": "prompt.txt", "runs": runs_value,
                     "cases": [{"id": "c", "input": "x", "assert": []}]}
            self.write("prompt.txt", STRICT_PROMPT)
            path = self.write("raw.json", json.dumps(suite))
            code, _, err = self.cli(["run", "--suite", path])
            self.assertEqual(code, 1, runs_value)
            self.assertTrue("run count" in err or "field 'runs'" in err, err)
            self.assertIn("positive integer", err)

    def test_cli_runs_zero_and_negative_exit1(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        for bad in ("0", "-3"):
            code, _, err = self.cli(["run", "--suite", path, "--runs", bad])
            self.assertEqual(code, 1, bad)
            self.assertIn("run count", err)

    def test_cli_runs_non_integer_exit1(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        code, _, err = self.cli(["run", "--suite", path, "--runs", "abc"])
        self.assertEqual(code, 1)
        self.assertIn("bad usage", err)

    def test_missing_required_cli_args_exit1(self):
        code, _, err = self.cli(["run"])
        self.assertEqual(code, 1)
        code, _, err = self.cli(["frobnicate"])
        self.assertEqual(code, 1)

    def test_missing_prompt_file_exit4(self):
        self.write("prompt.txt", STRICT_PROMPT)
        suite = {"name": "s", "prompt_file": "missing.txt",
                 "cases": [{"id": "c", "input": "x", "assert": []}]}
        path = self.write("raw.json", json.dumps(suite))
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 4)
        self.assertIn("prompt file", err)
        self.assertIn("missing.txt", err)

    def test_missing_input_file_exit4(self):
        path = self.suite_file([{"id": "c", "input": {"file": "gone.txt"}, "assert": []}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 4)
        self.assertIn("input file", err)
        self.assertIn("gone.txt", err)


# ---------------------------------------------------------------------------
# run: end-to-end behavior (SPEC 3 output table, SPEC 5 report, SPEC 7 flaky)
# ---------------------------------------------------------------------------

class RunEndToEndTests(HarnessTestCase):
    def test_pass_exit0_and_report_shape(self):
        path = self.suite_file(
            [
                {"id": "c1", "input": "I was charged twice for invoice 7",
                 "assert": [{"type": "json_valid"},
                            {"type": "json_field_equals", "field": "category",
                             "value": "billing"}]},
                {"id": "c2", "input": "hello",
                 "assert": [{"type": "json_field_equals", "field": "category",
                             "value": "general"},
                            {"type": "finish_is", "value": "stop"}]},
            ],
            runs=2,
        )
        code, out, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        report = json.loads(out)

        pairs = json.loads(out, object_pairs_hook=lambda p: p)
        self.assertEqual([k for k, _ in pairs],
                         ["suite", "prompt_file", "prompt_hash", "runs", "model",
                          "totals", "cases"])
        self.assertEqual([k for k, _ in dict(pairs)["totals"]],
                         ["cases", "passed", "failed", "flaky", "tokens_in",
                          "tokens_out", "wall_ms"])
        self.assertEqual(report["suite"], "test-suite")
        self.assertEqual(report["runs"], 2)
        self.assertEqual(report["model"], {"temperature": 0.0, "max_tokens": 256})
        self.assertEqual(report["prompt_file"], "prompt.txt")
        self.assertRegex(report["prompt_hash"], r"^[0-9a-f]{12}$")
        totals = report["totals"]
        self.assertEqual(totals["cases"], totals["passed"] + totals["failed"] + totals["flaky"])
        self.assertEqual(totals["cases"], 2)
        self.assertEqual(totals["passed"], 2)
        for case in report["cases"]:
            self.assertEqual([k for k, _ in json.loads(
                json.dumps(case), object_pairs_hook=lambda p: p)],
                ["id", "status", "pass_rate", "tokens_out_avg", "assertions", "failures"])
            self.assertEqual(case["status"], "pass")
            self.assertEqual(case["pass_rate"], 1.0)
            self.assertEqual(case["failures"], [])
            for entry in case["assertions"]:
                self.assertEqual(entry["passed"] + entry["failed"], 2)

    def test_failure_exit2_and_failure_detail_shape(self):
        path = self.suite_file(
            [{"id": "c1", "input": "I was charged twice for invoice 7",
              "assert": [{"type": "json_valid"},
                         {"type": "not_contains", "value": "Sure"},
                         {"type": "finish_is", "value": "stop"}]}],
            prompt_text=CHATTY_PROMPT,
        )
        code, out, _ = self.cli(["run", "--suite", path])
        self.assertEqual(code, 2)
        report = json.loads(out)
        case = report["cases"][0]
        self.assertEqual(case["status"], "fail")
        self.assertEqual(case["pass_rate"], 0.0)
        self.assertEqual(len(case["failures"]), 2)  # json_valid + not_contains

        failure = case["failures"][0]
        self.assertEqual([k for k, _ in json.loads(
            json.dumps(failure), object_pairs_hook=lambda p: p)],
            ["run_index", "assertion_type", "expected", "actual", "message"])
        self.assertEqual(failure["run_index"], 1)
        self.assertEqual(failure["assertion_type"], "json_valid")
        self.assertLessEqual(len(failure["actual"]), 203)

        by_type = {entry["type"]: entry for entry in case["assertions"]}
        self.assertEqual(by_type["json_valid"], {"type": "json_valid", "passed": 0, "failed": 1})
        self.assertEqual(by_type["not_contains"], {"type": "not_contains", "passed": 0, "failed": 1})
        self.assertEqual(by_type["finish_is"], {"type": "finish_is", "passed": 1, "failed": 0})

    def test_flaky_case_from_alternating_model(self):
        log = self.tmp / "calls.log"
        os.environ["FAKE_MODEL_LOG"] = str(log)
        alternating = self.fake_model(
            "import json, os\n"
            "count = 0\n"
            "log = os.environ['FAKE_MODEL_LOG']\n"
            "if os.path.exists(log):\n"
            "    with open(log, encoding='utf-8') as f:\n"
            "        count = sum(1 for _ in f)\n"
            "with open(log, 'a', encoding='utf-8') as f:\n"
            "    f.write('x\\n')\n"
            "out = '{\"category\": \"billing\"}' if count % 2 == 0 else 'not json'\n"
            "print(json.dumps({'output': out, 'tokens_in': 1, 'tokens_out': 1,"
            " 'finish': 'stop', 'latency_ms': 1}))\n"
        )
        os.environ["PROMPTLAB_MODEL_BIN"] = alternating
        path = self.suite_file(
            [{"id": "c1", "input": "x", "assert": [{"type": "json_valid"}]}],
            runs=2,
        )
        code, out, _ = self.cli(["run", "--suite", path])
        self.assertEqual(code, 2)
        report = json.loads(out)
        case = report["cases"][0]
        self.assertEqual(case["status"], "flaky")
        self.assertEqual(case["pass_rate"], 0.5)
        self.assertEqual(case["assertions"],
                         [{"type": "json_valid", "passed": 1, "failed": 1}])
        self.assertEqual(report["totals"]["flaky"], 1)

    def test_determinism_at_temperature_zero(self):
        path = self.suite_file(
            [{"id": "c1", "input": "I was charged twice for invoice 7",
              "assert": [{"type": "json_valid"},
                         {"type": "json_field_equals", "field": "category",
                          "value": "billing"},
                         {"type": "max_tokens", "value": 40}]}],
            runs=2,
        )
        _, first, _ = self.cli(["run", "--suite", path])
        _, second, _ = self.cli(["run", "--suite", path])
        report_one, report_two = json.loads(first), json.loads(second)
        report_one["totals"].pop("wall_ms")
        report_two["totals"].pop("wall_ms")
        self.assertEqual(report_one, report_two)
        self.assertEqual(json.dumps(report_one), json.dumps(report_two))

    def test_out_flag_writes_file_summary_on_stderr(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        out_path = self.tmp / "report.json"
        code, out, err = self.cli(["run", "--suite", path, "--out", str(out_path)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("result: PASS", err)
        report = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(report["totals"]["cases"], 1)

    def test_report_flag_appends_summary_to_stdout(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        code, out, err = self.cli(["run", "--suite", path, "--report"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn('"totals"', out)
        self.assertTrue(out.rstrip().endswith("result: PASS"))

    def test_out_and_report_summary_on_stdout(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        out_path = self.tmp / "report.json"
        code, out, err = self.cli(["run", "--suite", path,
                                   "--out", str(out_path), "--report"])
        self.assertEqual(code, 0)
        self.assertNotIn('"totals"', out)
        self.assertEqual(err, "")
        self.assertIn("result: PASS", out)
        json.loads(out_path.read_text(encoding="utf-8"))

    def test_cli_runs_overrides_suite_runs(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}], runs=2)
        code, out, _ = self.cli(["run", "--suite", path, "--runs", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["runs"], 1)

    def test_empty_cases_list_is_valid(self):
        path = self.suite_file([])
        code, out, _ = self.cli(["run", "--suite", path])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["totals"],
                         {"cases": 0, "passed": 0, "failed": 0, "flaky": 0,
                          "tokens_in": 0, "tokens_out": 0, "wall_ms": 0})

    def test_empty_assert_list_auto_passes(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}], runs=3)
        code, out, _ = self.cli(["run", "--suite", path])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["cases"][0]["pass_rate"], 1.0)
        self.assertEqual(report["cases"][0]["assertions"], [])

    def test_input_file_form(self):
        self.write("input.txt", "I was charged twice for invoice 7")
        path = self.suite_file(
            [{"id": "c", "input": {"file": "input.txt"},
              "assert": [{"type": "json_field_equals", "field": "category",
                          "value": "billing"}]}],
        )
        code, out, _ = self.cli(["run", "--suite", path])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["cases"][0]["status"], "pass")

    def test_seed_and_call_index_passthrough_and_exact_flags(self):
        log = self.tmp / "argv.log"
        os.environ["FAKE_MODEL_LOG"] = str(log)
        echo_args = self.fake_model(
            "import json, os, sys\n"
            "with open(os.environ['FAKE_MODEL_LOG'], 'a', encoding='utf-8') as f:\n"
            "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "print(json.dumps({'output': 'ok', 'tokens_in': 1, 'tokens_out': 1,"
            " 'finish': 'stop', 'latency_ms': 1}))\n"
        )
        os.environ["PROMPTLAB_MODEL_BIN"] = echo_args
        path = self.suite_file(
            [{"id": "c", "input": "x", "assert": []}],
            model={"temperature": 0.0, "max_tokens": 128, "seed": 7, "call_index": 3},
        )
        code, _, _ = self.cli(["run", "--suite", path])
        self.assertEqual(code, 0)
        argv = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        for token in ("--prompt", "--input", "--temperature", "0.0",
                      "--max-tokens", "128", "--seed", "7", "--call-index", "3"):
            self.assertIn(token, argv)
        self.assertNotIn("--prompt-file", argv)
        self.assertNotIn("--input-file", argv)


class ModelFailureTests(HarnessTestCase):
    def test_model_binary_not_found_exit3_names_locations(self):
        os.environ.pop("PROMPTLAB_MODEL_BIN", None)
        os.chdir(self.tmp)
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 3)
        self.assertIn("PROMPTLAB_MODEL_BIN", err)
        self.assertIn("stubmodel.py", err)
        self.assertIn("current working directory", err)
        self.assertIn("suite file", err)

    def test_model_timeout_exit3(self):
        slow = self.fake_model("import time\ntime.sleep(10)\n")
        os.environ["PROMPTLAB_MODEL_BIN"] = slow
        original = pl.MODEL_TIMEOUT_SECONDS
        pl.MODEL_TIMEOUT_SECONDS = 1
        self.addCleanup(setattr, pl, "MODEL_TIMEOUT_SECONDS", original)
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 3)
        self.assertEqual(err.strip(), "model binary did not respond within 30s")

    def test_model_unparseable_output_exit3(self):
        garbage = self.fake_model("print('this is not json')\n")
        os.environ["PROMPTLAB_MODEL_BIN"] = garbage
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 3)
        self.assertIn("could not be parsed as JSON", err)

    def test_model_crash_exit3(self):
        crash = self.fake_model(
            "import sys\nsys.stderr.write('kaboom')\nsys.exit(5)\n"
        )
        os.environ["PROMPTLAB_MODEL_BIN"] = crash
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        code, _, err = self.cli(["run", "--suite", path])
        self.assertEqual(code, 3)
        self.assertIn("exit code 5", err)

    def test_unwritable_report_file_exit4(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        bad = os.path.join(str(self.tmp), "no-such-dir", "report.json")
        code, _, err = self.cli(["run", "--suite", path, "--out", bad])
        self.assertEqual(code, 4)
        self.assertIn("could not write report file", err)


# ---------------------------------------------------------------------------
# compare (SPEC 9)
# ---------------------------------------------------------------------------

class CompareTests(HarnessTestCase):
    @staticmethod
    def make_report(suite="s", prompt_hash="aaaa", model=None, cases=(),
                    tokens_in=100, tokens_out=50):
        return {
            "suite": suite,
            "prompt_file": "p.txt",
            "prompt_hash": prompt_hash,
            "runs": 1,
            "model": model or {"temperature": 0.0, "max_tokens": 256},
            "totals": {"cases": len(cases), "passed": len(cases), "failed": 0,
                       "flaky": 0, "tokens_in": tokens_in, "tokens_out": tokens_out,
                       "wall_ms": 1},
            "cases": [{"id": cid, "status": "pass", "pass_rate": rate,
                       "tokens_out_avg": 10, "assertions": [], "failures": []}
                      for cid, rate in cases],
        }

    def write_report(self, name, report):
        path = self.tmp / name
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return str(path)

    def test_classifications_lines_cost_and_summary(self):
        baseline = self.make_report(prompt_hash="aaaa", cases=[("c1", 1.0), ("c2", 0.5),
                                                               ("c3", 1.0), ("c5", 0.0)])
        candidate = self.make_report(prompt_hash="bbbb", cases=[("c1", 0.5), ("c2", 0.5),
                                                                ("c5", 1.0), ("c4", 1.0)],
                                     tokens_in=120, tokens_out=50)
        base_path = self.write_report("base.json", baseline)
        cand_path = self.write_report("cand.json", candidate)
        code, out, err = self.cli(["compare", "--baseline", base_path,
                                   "--candidate", cand_path])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(lines, [
            "c1: regressed (1.0 -> 0.5)",
            "c2: unchanged (0.5 -> 0.5)",
            "c3: removed (1.0 -> n/a)",
            "c5: improved (0.0 -> 1.0)",
            "c4: new (n/a -> 1.0)",
            "cost: tokens_in 100 -> 120 (delta +20, +20.00%) | "
            "tokens_out 50 -> 50 (delta +0, +0.00%)",
            "summary: 1 regressed, 1 improved, 1 unchanged, 1 new, 1 removed",
        ])

    def test_out_json_structure_and_pct_rules(self):
        baseline = self.make_report(cases=[("c1", 1.0)], tokens_in=0, tokens_out=0)
        candidate = self.make_report(cases=[("c1", 1.0), ("c2", 0.0)],
                                     tokens_in=5, tokens_out=7)
        base_path = self.write_report("base.json", baseline)
        cand_path = self.write_report("cand.json", candidate)
        diff_path = self.tmp / "diff.json"
        code, _, _ = self.cli(["compare", "--baseline", base_path,
                               "--candidate", cand_path, "--out", str(diff_path)])
        self.assertEqual(code, 0)
        diff = json.loads(diff_path.read_text(encoding="utf-8"))
        pairs = json.loads(diff_path.read_text(), object_pairs_hook=lambda p: p)
        self.assertEqual([k for k, _ in pairs],
                         ["baseline", "candidate", "warnings", "cost", "cases", "summary"])
        self.assertEqual(diff["baseline"], base_path)
        self.assertEqual(diff["candidate"], cand_path)
        self.assertEqual(diff["cost"]["tokens_in"],
                         {"baseline": 0, "candidate": 5, "delta": 5, "pct_change": None})
        self.assertEqual(diff["cost"]["tokens_out"],
                         {"baseline": 0, "candidate": 7, "delta": 7, "pct_change": None})
        self.assertEqual(diff["cases"]["c2"],
                         {"classification": "new", "baseline_pass_rate": None,
                          "candidate_pass_rate": 0.0})
        self.assertEqual(diff["summary"],
                         {"regressed": 0, "improved": 0, "unchanged": 1,
                          "new": 1, "removed": 0})

    def test_zero_delta_zero_baseline_gives_zero_pct(self):
        baseline = self.make_report(cases=[("c1", 1.0)], tokens_in=0, tokens_out=3)
        candidate = self.make_report(cases=[("c1", 1.0)], tokens_in=0, tokens_out=3)
        base_path = self.write_report("base.json", baseline)
        cand_path = self.write_report("cand.json", candidate)
        diff_path = self.tmp / "diff.json"
        self.cli(["compare", "--baseline", base_path, "--candidate", cand_path,
                  "--out", str(diff_path)])
        cost = json.loads(diff_path.read_text(encoding="utf-8"))["cost"]
        self.assertEqual(cost["tokens_in"]["pct_change"], 0.0)

    def test_warnings(self):
        baseline = self.make_report(suite="a", prompt_hash="same123",
                                    model={"temperature": 0.0, "max_tokens": 256})
        candidate = self.make_report(suite="b", prompt_hash="same123",
                                     model={"temperature": 0.5, "max_tokens": 256})
        base_path = self.write_report("base.json", baseline)
        cand_path = self.write_report("cand.json", candidate)
        code, out, _ = self.cli(["compare", "--baseline", base_path,
                                 "--candidate", cand_path])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("WARNING: "))
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("WARNING:")]), 3)
        diff_path = self.tmp / "diff.json"
        self.cli(["compare", "--baseline", base_path, "--candidate", cand_path,
                  "--out", str(diff_path)])
        warnings = json.loads(diff_path.read_text(encoding="utf-8"))["warnings"]
        self.assertEqual(len(warnings), 3)

    def test_no_warnings_when_compatible(self):
        baseline = self.make_report(prompt_hash="aaaa", cases=[("c1", 1.0)])
        candidate = self.make_report(prompt_hash="bbbb", cases=[("c1", 0.0)])
        base_path = self.write_report("base.json", baseline)
        cand_path = self.write_report("cand.json", candidate)
        code, out, _ = self.cli(["compare", "--baseline", base_path,
                                 "--candidate", cand_path])
        self.assertEqual(code, 0)
        self.assertNotIn("WARNING", out)
        self.assertIn("c1: regressed (1.0 -> 0.0)", out)

    def test_missing_report_file_exit4(self):
        path = self.write_report("base.json", self.make_report())
        code, _, err = self.cli(["compare", "--baseline", path,
                                 "--candidate", str(self.tmp / "nope.json")])
        self.assertEqual(code, 4)
        self.assertIn("could not read candidate report file", err)

    def test_malformed_report_json_exit1(self):
        base_path = self.write_report("base.json", self.make_report())
        cand_path = self.write("cand.json", "{broken")
        code, _, err = self.cli(["compare", "--baseline", base_path,
                                 "--candidate", cand_path])
        self.assertEqual(code, 1)
        self.assertIn("malformed JSON", err)


# ---------------------------------------------------------------------------
# doctor (SPEC 10)
# ---------------------------------------------------------------------------

class DoctorTests(HarnessTestCase):
    def test_all_lines_in_order_and_exit0(self):
        (self.tmp / "suites").mkdir()
        (self.tmp / "suites" / "demo.json").write_text("{}", encoding="utf-8")
        os.chdir(self.tmp)
        code, out, err = self.cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        expected = [
            f"[{'PASS' if sys.version_info >= (3, 10) else 'FAIL'}] python",
            "[PASS] model",
            "[PASS] suites",
            "[PASS] assertions",
        ]
        self.assertEqual(out.splitlines(), expected)

    def test_failures_still_exit0(self):
        os.environ.pop("PROMPTLAB_MODEL_BIN", None)
        os.chdir(self.tmp)  # empty dir: no stubmodel.py, no suites/, no *.json
        code, out, _ = self.cli(["doctor"])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[1], "[FAIL] model")
        self.assertEqual(lines[2], "[FAIL] suites")
        self.assertEqual(lines[3], "[PASS] assertions")


# ---------------------------------------------------------------------------
# stubmodel binary contract (SPEC 2)
# ---------------------------------------------------------------------------

class StubModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stubmodel-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def prompt_file(self, text=STRICT_PROMPT):
        path = self.tmp / "prompt.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_stub(self, *extra):
        return subprocess.run(
            [sys.executable, STUB_BIN, *extra],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def test_output_envelope_keys(self):
        proc = self.run_stub("--prompt", self.prompt_file(), "--input", "hello")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(set(json.loads(proc.stdout)),
                         {"output", "tokens_in", "tokens_out", "finish", "latency_ms"})

    def test_temperature_zero_is_deterministic(self):
        prompt = self.prompt_file()
        one = self.run_stub("--prompt", prompt, "--input", "I was charged for invoice 3")
        two = self.run_stub("--prompt", prompt, "--input", "I was charged for invoice 3")
        self.assertEqual(one.stdout, two.stdout)

    def test_input_at_file_form(self):
        input_path = self.tmp / "input.txt"
        input_path.write_text("How do I delete my account?", encoding="utf-8")
        proc = self.run_stub("--prompt", self.prompt_file(),
                             "--input", "@" + str(input_path))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("account", json.loads(proc.stdout)["output"])

    def test_missing_prompt_file_exit3(self):
        proc = self.run_stub("--prompt", str(self.tmp / "gone.txt"), "--input", "x")
        self.assertEqual(proc.returncode, 3)

    def test_bad_arguments_exit2(self):
        proc = self.run_stub("--prompt")
        self.assertEqual(proc.returncode, 2)

    def test_max_tokens_truncation_sets_finish_length(self):
        proc = self.run_stub("--prompt", self.prompt_file(CHATTY_PROMPT),
                             "--input", "hello there", "--max-tokens", "4")
        data = json.loads(proc.stdout)
        self.assertLessEqual(data["tokens_out"], 4)
        self.assertEqual(data["finish"], "length")

    def test_seeded_high_temperature_is_reproducible(self):
        prompt = self.prompt_file()
        one = self.run_stub("--prompt", prompt, "--input", "hello",
                            "--temperature", "0.9", "--seed", "11")
        two = self.run_stub("--prompt", prompt, "--input", "hello",
                            "--temperature", "0.9", "--seed", "11")
        first = json.loads(one.stdout)
        second = json.loads(two.stdout)
        first.pop("latency_ms")
        second.pop("latency_ms")
        self.assertEqual(first, second)

    def test_token_formula(self):
        proc = self.run_stub("--prompt", self.prompt_file(), "--input", "abcd"*10)
        data = json.loads(proc.stdout)
        expected_in = -(-len(STRICT_PROMPT + "abcd" * 10) // 4)
        self.assertEqual(data["tokens_in"], expected_in)
        self.assertEqual(data["tokens_out"], -(-len(data["output"]) // 4))


# ---------------------------------------------------------------------------
# Real subprocess entry point (SPEC 3 exit codes at the OS level)
# ---------------------------------------------------------------------------

class CliSubprocessTests(HarnessTestCase):
    def run_harness(self, *argv, cwd=None):
        env = os.environ.copy()
        env["PROMPTLAB_MODEL_BIN"] = STUB_BIN
        return subprocess.run(
            [sys.executable, HARNESS, *argv],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            cwd=cwd or str(self.tmp), env=env,
        )

    def test_run_exit0_and_report_json_on_stdout(self):
        path = self.suite_file([{"id": "c", "input": "x", "assert": []}])
        proc = self.run_harness("run", "--suite", path)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["suite"], "test-suite")

    def test_missing_suite_exit4(self):
        proc = self.run_harness("run", "--suite", "missing.json")
        self.assertEqual(proc.returncode, 4)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)

    def test_unknown_command_exit1(self):
        proc = self.run_harness("wat")
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
