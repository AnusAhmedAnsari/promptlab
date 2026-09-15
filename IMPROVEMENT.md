# IMPROVEMENT.md — prompt iterations, evidenced by real runs

Method (SPEC.md Section 13): the suite `suites/classify_v2.json` and
`suites/classify_v1.json` share the same six cases and the same model settings
(temperature 0.0, max_tokens 256, runs 1). Between iterations ONLY the prompt
file changes, so every delta below is attributable to prompt wording. Each
iteration was executed with a real `python promptlab.py run` invocation; the
report JSON produced by that invocation is pasted verbatim below (`wall_ms` is
the spec's declared volatile field and naturally differs per execution).
Interim prompts are reproduced inline so every iteration is reproducible.

Summary table (from the pasted reports, not hand-counted):

| # | Prompt | Change | passed/failed | tokens_out | exit |
|---|--------|--------|---------------|------------|------|
| 1 | `classify_v1.txt` | baseline (category list + "answer with category and reason") | 1/5 | 382 | 2 |
| 2 | v1 + "Please answer concisely." | politeness/conciseness tweak — **did not help** | 1/5 | 382 | 2 |
| 3 | v1 + "Respond with raw JSON only - no prose..." | format lock | 6/0 | 198 | 0 |
| 4 | `classify_v2.txt` (full format spec + example) | final | 6/0 | 198 | 0 |

`promptlab compare` baseline (iteration 1) vs candidate (iteration 4):

```
$ python promptlab.py compare --baseline <v1 report> --candidate <v2 report>
c001: improved (0.0 -> 1.0)
c002: unchanged (1.0 -> 1.0)
c003: improved (0.0 -> 1.0)
c004: improved (0.0 -> 1.0)
c005: improved (0.0 -> 1.0)
c006: improved (0.0 -> 1.0)
cost: tokens_in 359 -> 1034 (delta +675, +188.02%) | tokens_out 382 -> 198 (delta -184, -48.17%)
summary: 0 regressed, 5 improved, 1 unchanged, 0 new, 0 removed
```

---

## Iteration 1 — baseline `prompts/classify_v1.txt`

Prompt text:

```
You are a customer-support ticket classifier.

Classify the user message into exactly one category:
billing, technical, shipping, account, general.

Answer with the category and a short reason.
```

Command: `python promptlab.py run --suite suites/classify_v1.json --out <report>`
(exit code 2, stderr summary `1 passed, 5 failed, 0 flaky`).

Report (verbatim):

```
{
  "suite": "classify-smoke",
  "prompt_file": "../prompts/classify_v1.txt",
  "prompt_hash": "d92180031a9c",
  "runs": 1,
  "model": {
    "temperature": 0.0,
    "max_tokens": 256
  },
  "totals": {
    "cases": 6,
    "passed": 1,
    "failed": 5,
    "flaky": 0,
    "tokens_in": 359,
    "tokens_out": 382,
    "wall_ms": 552
  },
  "cases": [
    {
      "id": "c001",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 63,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "not_contains",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "finish_is",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_valid",
          "expected": null,
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON (after fence stripping)"
        },
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "billing",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON; cannot resolve field"
        },
        {
          "run_index": 1,
          "assertion_type": "not_contains",
          "expected": "Sure",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output contains forbidden 'Sure'"
        }
      ]
    },
    {
      "id": "c002",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "matches",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c003",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "max_tokens",
          "passed": 0,
          "failed": 1
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "shipping",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"shipping\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword ...",
          "message": "output is not valid JSON; cannot resolve field"
        },
        {
          "run_index": 1,
          "assertion_type": "max_tokens",
          "expected": 40,
          "actual": 64,
          "message": "tokens_out 64 exceeds maximum 40"
        }
      ]
    },
    {
      "id": "c004",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "equals",
          "expected": "{\"category\": \"account\", \"confidence\": 0.9, \"meta\": {\"priority\": \"normal\", \"language\": \"en\"}, \"reason\": \"matched keyword 'account'\"}",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"account\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword '...",
          "message": "output does not equal expected value (after whitespace normalization)"
        },
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "en",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"account\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword '...",
          "message": "output is not valid JSON; cannot resolve field"
        }
      ]
    },
    {
      "id": "c005",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "not_contains",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "max_tokens",
          "passed": 0,
          "failed": 1
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "general",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"general\",\n  \"confidence\": 0.5,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"no strong keyword...",
          "message": "output is not valid JSON; cannot resolve field"
        },
        {
          "run_index": 1,
          "assertion_type": "not_contains",
          "expected": "Let me know",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"general\",\n  \"confidence\": 0.5,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"no strong keyword...",
          "message": "output contains forbidden 'Let me know'"
        },
        {
          "run_index": 1,
          "assertion_type": "max_tokens",
          "expected": 60,
          "actual": 64,
          "message": "tokens_out 64 exceeds maximum 60"
        }
      ]
    },
    {
      "id": "c006",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 63,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_valid",
          "expected": null,
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON (after fence stripping)"
        },
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "high",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON; cannot resolve field"
        }
      ]
    }
  ]
}
```

## Iteration 2 — "Please answer concisely." (change that did NOT help)

Full prompt text (v1 plus one line):

```
You are a customer-support ticket classifier.

Classify the user message into exactly one category:
billing, technical, shipping, account, general.

Answer with the category and a short reason.

Please answer concisely.
```

Command: `python promptlab.py run --suite suites/_iter2.json --out <report>`
(exit code 2). The suite is byte-identical to `classify_v1.json` except
`prompt_file` points at the interim prompt above.

Report (verbatim) — result: `1 passed, 5 failed, 0 flaky | tokens_in=398 tokens_out=382 | prompt_hash=4fb9a962d263`; per-case assertion
outcomes are identical to iteration 1, i.e. the conciseness request changed
nothing about format compliance:

```
{
  "suite": "classify-smoke",
  "prompt_file": "../prompts/_iter2_concise.txt",
  "prompt_hash": "4fb9a962d263",
  "runs": 1,
  "model": {
    "temperature": 0.0,
    "max_tokens": 256
  },
  "totals": {
    "cases": 6,
    "passed": 1,
    "failed": 5,
    "flaky": 0,
    "tokens_in": 398,
    "tokens_out": 382,
    "wall_ms": 495
  },
  "cases": [
    {
      "id": "c001",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 63,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "not_contains",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "finish_is",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_valid",
          "expected": null,
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON (after fence stripping)"
        },
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "billing",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON; cannot resolve field"
        },
        {
          "run_index": 1,
          "assertion_type": "not_contains",
          "expected": "Sure",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output contains forbidden 'Sure'"
        }
      ]
    },
    {
      "id": "c002",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "matches",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c003",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "max_tokens",
          "passed": 0,
          "failed": 1
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "shipping",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"shipping\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword ...",
          "message": "output is not valid JSON; cannot resolve field"
        },
        {
          "run_index": 1,
          "assertion_type": "max_tokens",
          "expected": 40,
          "actual": 64,
          "message": "tokens_out 64 exceeds maximum 40"
        }
      ]
    },
    {
      "id": "c004",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "equals",
          "expected": "{\"category\": \"account\", \"confidence\": 0.9, \"meta\": {\"priority\": \"normal\", \"language\": \"en\"}, \"reason\": \"matched keyword 'account'\"}",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"account\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword '...",
          "message": "output does not equal expected value (after whitespace normalization)"
        },
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "en",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"account\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword '...",
          "message": "output is not valid JSON; cannot resolve field"
        }
      ]
    },
    {
      "id": "c005",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 64,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "not_contains",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "max_tokens",
          "passed": 0,
          "failed": 1
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "general",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"general\",\n  \"confidence\": 0.5,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"no strong keyword...",
          "message": "output is not valid JSON; cannot resolve field"
        },
        {
          "run_index": 1,
          "assertion_type": "not_contains",
          "expected": "Let me know",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"general\",\n  \"confidence\": 0.5,\n  \"meta\": {\n    \"priority\": \"normal\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"no strong keyword...",
          "message": "output contains forbidden 'Let me know'"
        },
        {
          "run_index": 1,
          "assertion_type": "max_tokens",
          "expected": 60,
          "actual": 64,
          "message": "tokens_out 64 exceeds maximum 60"
        }
      ]
    },
    {
      "id": "c006",
      "status": "fail",
      "pass_rate": 0.0,
      "tokens_out_avg": 63,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "json_field_equals",
          "passed": 0,
          "failed": 1
        },
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": [
        {
          "run_index": 1,
          "assertion_type": "json_valid",
          "expected": null,
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON (after fence stripping)"
        },
        {
          "run_index": 1,
          "assertion_type": "json_field_equals",
          "expected": "high",
          "actual": "Sure! Here is the classification of your message.\n```json\n{\n  \"category\": \"billing\",\n  \"confidence\": 0.9,\n  \"meta\": {\n    \"priority\": \"high\",\n    \"language\": \"en\"\n  },\n  \"reason\": \"matched keyword 'ch...",
          "message": "output is not valid JSON; cannot resolve field"
        }
      ]
    }
  ]
}
```

Verdict: no case changed status; tokens_in rose 359 -> 398 (longer prompt) with
zero quality gain. Reverted the added line.

## Iteration 3 — "Respond with raw JSON only"

Full prompt text (v1 plus one line):

```
You are a customer-support ticket classifier.

Classify the user message into exactly one category:
billing, technical, shipping, account, general.

Answer with the category and a short reason.

Respond with raw JSON only - no prose before or after the JSON object.
```

Command: `python promptlab.py run --suite suites/_iter3.json --out <report>`
(exit code 0).

Report (verbatim) — result: `6 passed, 0 failed, 0 flaky | tokens_in=467 tokens_out=198 | prompt_hash=03d250478f2f`:

```
{
  "suite": "classify-smoke",
  "prompt_file": "../prompts/_iter3_rawjson.txt",
  "prompt_hash": "03d250478f2f",
  "runs": 1,
  "model": {
    "temperature": 0.0,
    "max_tokens": 256
  },
  "totals": {
    "cases": 6,
    "passed": 6,
    "failed": 0,
    "flaky": 0,
    "tokens_in": 467,
    "tokens_out": 198,
    "wall_ms": 574
  },
  "cases": [
    {
      "id": "c001",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "not_contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "finish_is",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c002",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "matches",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c003",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "max_tokens",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c004",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c005",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "not_contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "max_tokens",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c006",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    }
  ]
}
```

## Iteration 4 — final `prompts/classify_v2.txt` (full format spec + example)

Command: `python promptlab.py run --suite suites/classify_v2.json --out <report>`
(exit code 0, stderr summary `6 passed, 0 failed, 0 flaky`).

Report (verbatim) — result: `6 passed, 0 failed, 0 flaky | tokens_in=1034 tokens_out=198 | prompt_hash=a97ac90b04d7`:

```
{
  "suite": "classify-smoke",
  "prompt_file": "../prompts/classify_v2.txt",
  "prompt_hash": "a97ac90b04d7",
  "runs": 1,
  "model": {
    "temperature": 0.0,
    "max_tokens": 256
  },
  "totals": {
    "cases": 6,
    "passed": 6,
    "failed": 0,
    "flaky": 0,
    "tokens_in": 1034,
    "tokens_out": 198,
    "wall_ms": 480
  },
  "cases": [
    {
      "id": "c001",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "not_contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "finish_is",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c002",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "matches",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c003",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "max_tokens",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c004",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c005",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "not_contains",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "max_tokens",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    },
    {
      "id": "c006",
      "status": "pass",
      "pass_rate": 1.0,
      "tokens_out_avg": 33,
      "assertions": [
        {
          "type": "json_valid",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "json_field_equals",
          "passed": 1,
          "failed": 0
        },
        {
          "type": "contains",
          "passed": 1,
          "failed": 0
        }
      ],
      "failures": []
    }
  ]
}
```

Determinism check (SPEC 5) — the iteration-4 suite was run twice; after
removing `totals.wall_ms` (480 vs 524 ms) the two reports compare equal as
objects AND as serialized bytes (`json.dumps` equality checked):

```
wall_ms run1=480 run2=524 (only volatile field)
reports identical after removing wall_ms: True
```

Compare diff JSON (written by the same invocation as the compare above,
`--out` flag) — `pct_change` values follow SPEC 9 (`round(delta/baseline*100, 2)`):

```
{
  "baseline": "../.tmp-promptlab-artifacts/classify_v1.json",
  "candidate": "../.tmp-promptlab-artifacts/classify_v2.json",
  "warnings": [],
  "cost": {
    "tokens_in": {
      "baseline": 359,
      "candidate": 1034,
      "delta": 675,
      "pct_change": 188.02
    },
    "tokens_out": {
      "baseline": 382,
      "candidate": 198,
      "delta": -184,
      "pct_change": -48.17
    }
  },
  "cases": {
    "c001": {
      "classification": "improved",
      "baseline_pass_rate": 0.0,
      "candidate_pass_rate": 1.0
    },
    "c002": {
      "classification": "unchanged",
      "baseline_pass_rate": 1.0,
      "candidate_pass_rate": 1.0
    },
    "c003": {
      "classification": "improved",
      "baseline_pass_rate": 0.0,
      "candidate_pass_rate": 1.0
    },
    "c004": {
      "classification": "improved",
      "baseline_pass_rate": 0.0,
      "candidate_pass_rate": 1.0
    },
    "c005": {
      "classification": "improved",
      "baseline_pass_rate": 0.0,
      "candidate_pass_rate": 1.0
    },
    "c006": {
      "classification": "improved",
      "baseline_pass_rate": 0.0,
      "candidate_pass_rate": 1.0
    }
  },
  "summary": {
    "regressed": 0,
    "improved": 5,
    "unchanged": 1,
    "new": 0,
    "removed": 0
  }
}
```

Conclusion: v2 measurably outperforms v1 (5 improved / 1 unchanged / 0
regressed; tokens_out nearly halved 382 -> 198) because the "raw JSON only"
format lock plus an explicit key schema removes the chatty preamble/fenced
output that failed `json_valid`, `json_field_equals`, `not_contains`,
`equals`, and `max_tokens` under v1. The unchanged case c002 only asserts
substring/regex presence, which the fenced v1 output already satisfied.
