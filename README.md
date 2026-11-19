# Weekly Skill: Evidence-Gated Experiment Planning

Version: 1.0.0

A portable Agent Skill for source-grounded generation, comparison, and revision of scientific experiment plans. It combines scientific review with deterministic checks of finite parameter domains, line-item costs, resource calendars, candidate changes, and original output contracts.

## Contents

- `SKILL.md`: main auto-discoverable workflow and non-negotiable boundaries.
- `references/`: compact science/risk guidance, dynamic contract handling, method bibliography, and usage.
- `scripts/case_io.py`: dynamic contract skeleton/validation, source inventory, atomic records, and replayable candidate diffs.
- `scripts/plan_audit.py`: source attachment, exact domains, quantity/cost calculations, scientific-check separation, bounded-search reporting and comparison.
- `scripts/schedule.py`: exact half-open interval/resource-capacity verification and deterministic prospective schedule generation.
- `scripts/pdf_tools.py`: actual-PDF text extraction, named-page rendering, optional OCR, and parser-error/provenance manifests. Uses declared command-line tools or available PyMuPDF/pypdf as conditional integrations, never an answer layer.
- `scripts/state_consistency.py`: type-sensitive comparisons of explicitly paired current-state fields, with separate original/revised scopes and `not_run` for unresolved mappings.
- `scripts/run_clock.py`: advisory elapsed-time checkpoints starting at the first helper call; it cannot measure earlier model time or interrupt a long model turn.
- `schemas/plan-audit.schema.json`: the optional internal normalized audit format; **not** the original case schema.
- `examples/`: small invented interface fixtures, not official cases, scientific answers, prices, or future results.
- `VERSION`: release identifier.

## Dependencies and installation

Python 3.9+ standard library, tested against the local 3.9 series by design. No network access, third-party Python package, global installation, private file, account, or external solver is needed for these helpers. Actual scientific source extraction may use the environment's declared PDF/OCR/scientific tools; record whichever were really used.

Install this directory as `weekly-skill` under the harness's configured skill root. In the evaluator this is `/skills/weekly-skill`. Do not nest a second submission or skill folder around `SKILL.md`. Its name is intentionally `weekly-skill`, and automatic discovery is not disabled.

## Typical run

Read `references/usage.md`, actual task instructions and input contract, then follow `SKILL.md`. The evaluator-facing inputs are `/input/case.json` and the provided task. Work in `/app/work`; write `/app/output/result.json` with the literal case identifier, all original output-contract fields, truthful generation status, evidence, uncertainties, and changes.

The examine-plan/validate commands are:

```bash
python3 scripts/case_io.py init \
  --case /input/case.json --work /app/work --task /input/task.md \
  --output /app/output/result.json
python3 scripts/plan_audit.py audit \
  --input /app/work/plan-audit.json --case /input/case.json \
  --source-root /input --output /app/output/validation.json
python3 scripts/case_io.py validate \
  --case /input/case.json --result /app/output/result.json \
  --output /app/output/contract-validation.json
```

Use local paths when developing. File and source locators are validated relative to explicitly supplied roots. Script locations resolve through `__file__`, not the caller's CWD.

## Independent review responsibility

A `machine_pass` or JSON schema success is not proof of a valid control, correct source interpretation, unit semantics, material equivalence, adequate statistical power, safe operations, actual booking, or ethical/legal approval. Do not rank a scientifically failed candidate above a sound one using a lower price. Heuristic/partial search must disclose its coverage. Unknowns are not zeros, and valid non-detection is not zero effect.

The helpers are deliberately limited to common contract types and explicit numeric/calendar representations. Advanced schema combinators, incompatible units, unclear discounts, unsupported calendars, ambiguous substitutions, and complex statistical models need explicit uncertainty, another suitable tool, or expert review. Retain a truthful partial rather than fabricate a result.

## Maintenance and reuse

- Preserve the frontmatter name/description and file paths as one portable unit.
- Before release, run the scripts on the synthetic interface examples plus edge/fault inputs, and exercise actual Skill loading in the target DeepSeek Harness version when accessible.
- If original evaluator output contracts vary, adapt through `case_io.py`, not by hard-coding fields in `SKILL.md`.
- If scheduling semantics change, preserve source-defined nonpreemption, capacity, release, and availability rules rather than weakening checks.
- Store only UTF-8 text resources (at most 50 files, ≤500 KB each, ≤2 MB total, no symlinks). Do not include real case answer layers, credentials, binaries, caches, virtual environments, or formal generated outputs.

The method sources used for design are listed in `references/references.md`. Performance and environmental claims must be based on fresh runnable evidence; no baseline improvement or official score is embedded in this artifact. The released code and resources are distributed under the MIT License; see `LICENSE`.
