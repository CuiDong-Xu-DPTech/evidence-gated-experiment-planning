# Use and minimal example

## Install and invoke

Install the complete directory as a skill named `weekly-skill` under the harness's configured skill root (`/skills/weekly-skill` in the challenge evaluator). No package installation is required; Python 3.9+ and the supplied scientific/source-reading tools are sufficient. Follow the runtime's declared `environment/resources.yaml` for optional PDF/OCR capability.

Use a natural task such as:

```text
Read /input/case.json and /input/task.md. Compare and, where justified, revise all supplied experimental candidates using the actual sources and prospective resource/booking constraints. Preserve the original output_contract and case_id. Write /app/output/result.json with honest evidence, uncertainties, validation, and version changes.
```

The description also supports ordinary experiment-plan generation, revision, variable/control design, finite-domain feasibility, and prospective resource-schedule review. A successful trigger is the harness actually loading the Skill, not merely repeating its name in a prompt.

## Commands

From the official-style paths:

```bash
python3 /skills/weekly-skill/scripts/run_clock.py start --work /app/work
python3 /skills/weekly-skill/scripts/case_io.py init \
  --case /input/case.json --work /app/work \
  --task /input/task.md --output /app/output/result.json
python3 /skills/weekly-skill/scripts/case_io.py snapshot \
  --case /input/case.json --input-root /input --work /app/work
# Read the real task/materials; create scientific candidates and plan-audit.json.
python3 /skills/weekly-skill/scripts/plan_audit.py audit \
  --input /app/work/plan-audit.json --case /input/case.json \
  --source-root /input --output /app/output/validation.json
python3 /skills/weekly-skill/scripts/case_io.py validate \
  --case /input/case.json --result /app/output/result.json \
  --output /app/output/contract-validation.json
```

For a local installation, replace `/skills/weekly-skill` with its actual absolute path and use local input/work/output paths. Do not put an extra copy of the skill inside a `submission` directory when installing it.

## Clearly synthetic interface example

The following is invented **only to show the outer interface**. It is not a formal case, benchmark input, scientific recommendation, or future result:

```json
{
  "case_id": "synthetic-deidentified-demo",
  "output_contract": {
    "type": "object",
    "properties": {
      "case_id": {"type": "string"},
      "recommended_candidate_id": {"type": "string"},
      "plan_summary": {"type": "string"},
      "status": {"type": "string"},
      "sources": {"type": "array"},
      "uncertainty": {"type": "array"},
      "change_records": {"type": "array"}
    },
    "required": ["case_id", "recommended_candidate_id", "plan_summary", "status", "sources", "uncertainty", "change_records"]
  }
}
```

`plan-audit.json` may contain three synthetic source candidates with provisional quantities and a deliberately invalid choice, to demonstrate that the audit records both:

```text
candidate-a: known arithmetic/domain/schedule properties + any unresolved review
candidate-b: a detected domain/cost/resource violation, preserved rather than hidden
candidate-c: a proposed alternative with explicit pending calendar or expert information
```

A final example-shaped result might say:

```json
{
  "case_id": "synthetic-deidentified-demo",
  "recommended_candidate_id": "candidate-a",
  "plan_summary": "SYNTHETIC INTERFACE EXAMPLE ONLY; no real scientific recommendation or measured result is made.",
  "status": "complete",
  "sources": [{"id": "synthetic-contract", "kind": "organizer_contract", "locator": "/synthetic/input"}],
  "uncertainty": [{"kind": "synthetic_example", "description": "This interface example does not validate any science, availability, approval, or future response."}],
  "change_records": []
}
```

For the complete machine-auditable synthetic input, see `examples/input.json`. `examples/audit.example.json` is its generated audit report, deliberately demonstrating one passing candidate, one domain/cost failure, and a pending schedule. Running this example therefore returns exit code 2 intentionally; its nonzero result is part of the negative-case illustration, not a verified experiment or a successful score. These are interface fixtures, not official answers. Filesystem paths inside that static example report are illustrative snapshots, not dependencies on the author's machine. The example schema is illustrative, and real runs must instead read the actual `output_contract`.

## Self-check and troubleshooting

- **No valid skill trigger:** confirm `<configured-root>/weekly-skill/SKILL.md`, YAML name/description, and no `disable-model-invocation` override. Use the harness's actual skill log to verify loading.
- **No output or truncated output:** do not restart from zero; keep the last valid partial, read the issue list, and prioritize case_id plus contract restoration.
- **Missing PDF layer:** use the actual declared PDF parser and render/inspect affected pages. Do not fall back to a filename or memory for a scientific value.
- **Validator reports unknown:** supply the missing real fact or label it unresolved. Do not choose a value to remove an inconvenient warning.
- **No feasible candidate:** state coverage actually searched and concrete constraint conflicts. Do not claim that unsearched candidates cannot work or silently modify a hard constraint.
- **Candidate changes:** record the actual parent and pointers, replay the generated diff, and revalidate affected science, arithmetic, and calendars.

The standard-library scripts have no network requirement. Method references are background reading, not sources for current case facts.
