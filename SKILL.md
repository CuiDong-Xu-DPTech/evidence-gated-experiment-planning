---
name: weekly-skill
description: Generates, compares, and revises source-grounded scientific experiment plans under explicit constraints. Use for experiment or protocol planning/revision, candidate-plan comparison, hypotheses and variables, controls, finite parameter domains, instrument/material feasibility, prospective budgets and booking schedules, scientific PDFs with case.json/output_contract inputs, and risk, failure, uncertainty, or validation planning.
---

# Evidence-Gated Experiment Planning

Turn the **actual supplied scientific sources and constraints** into plans that can be scheduled, audited, and revised. The scripts address representation, arithmetic, domains, resource calendars, contracts, and version integrity; they do not prove scientific validity, source entailment, safety, or external approval.

## Non-negotiables

- Read the real case, task, and sources. A domain label, filename, citation title, or memory is not evidence for missing content.
- Read the original `output_contract` before designing the result. Preserve every required field, its original meaning/type, and the literal `case_id`; do not replace it with a generic fixed schema.
- Preserve every supplied candidate/version identity. Compare before revising; never merge candidates into average advice or substitute prewritten answers. The usual three candidates means three **source candidates**, not three mandatory fabricated plans.
- Keep scientific adequacy, feasibility, and approval separate. Never trade away a necessary control, scientific comparison, or safety constraint for price or speed. A lower cost cannot compensate for an invalid design.
- Use only permitted parameter values and explicit substitutions. Do not clamp values, invent discounts, assume missing price/time/stock is zero, or call a proposed slot booked.
- Unknown, missing input, resource conflict, scientific undecidability, and tool failure are different outcomes. Preserve them explicitly. Never invent observed future responses or expert approval.

## Workflow

### 1. Establish the runtime and protect the contract

Determine the skill directory from the loader-provided resource base; scripts independently resolve their own location with `Path(__file__).resolve().parents[1]`. Do not depend on the caller's current directory.

Use the contracted `/input`, `/app/work`, and `/app/output` in evaluation. Resolve task instructions in this order only: `/input/task.md`, `/app/work/task.md`, then `$PWD/task.md`. Look for `environment/resources.yaml` only in the corresponding `/app`, `/input`, and `/app/work` locations. If absent, inventory tools actually available and record the missing manifest rather than claiming it was read.

Read [references/contract.md](references/contract.md) before transforming data. Create the work/output directories and run:

```bash
python3 "$SKILL_ROOT/scripts/run_clock.py" start --work /app/work
python3 "$SKILL_ROOT/scripts/case_io.py" init \
  --case /input/case.json --work /app/work \
  --task /input/task.md --output /app/output/result.json
python3 "$SKILL_ROOT/scripts/case_io.py" snapshot \
  --case /input/case.json --input-root /input --work /app/work
```

Keep the emitted contract descriptor and uncertainty records. If initialization fails, save the best honest partial result with all currently known original fields instead of inventing a replacement schema. Write progress and artifacts under `/app/work`, then atomically update final artifacts under `/app/output`.

### 2. Build the evidence and constraint representation

Inventory the supplied materials actually referenced by the case. Read `environment/resources.yaml` when available and prefer its declared scientific/PDF tools. For each actual PDF, set `ACTUAL_SOURCE_PDF` from the actual source inventory, then read it during this run (never import an answer layer):

Set `SOURCE_PAGES` to the actual sections needed for the scientific decisions, including source-informed methods, quantitative tables, and contradictory findings; use `all` when those decisions genuinely require the full document. Inspect enough surrounding context and do not claim a document-wide absence from a selective read.

```bash
python3 "$SKILL_ROOT/scripts/pdf_tools.py" extract \
  --pdf "$ACTUAL_SOURCE_PDF" --work /app/work/pdf --pages "$SOURCE_PAGES"
python3 "$SKILL_ROOT/scripts/pdf_tools.py" render \
  --pdf "$ACTUAL_SOURCE_PDF" --work /app/work/pdf \
  --pages "$DECISION_CRITICAL_PAGES" --dpi 160
```

The helper records source hashes, parser/tool output, exact PDF page mappings, sparse pages, rendering errors and warnings. Read those manifests and the extracted page text; do not assume success from a command that merely ran. A second parser is not an independent scientific source. Follow [references/pdf-tools.md](references/pdf-tools.md) for tool fallbacks, unreadable documents and page validation. Inspect relevant rendered pages with an actual available image/PDF viewer for tables, merged cells, signs, superscripts, Greek symbols, and OCR uncertainty. Append `--ocr` for a sparse/scanned relevant page, then check decision-critical values visually. If image inspection cannot be performed, record `not_run`; never pretend a missing text layer, font, figure, or tool means a scientific claim is absent. Record pages examined, actual tool commands/versions when obtainable, and unresolved critical facts.

Build a concise ledger in `/app/work/evidence.json` for each material constraint and scientific claim:

```text
ID | exact claim/value/unit | source class | artifact + locator | scope/conditions
   | direct observation / derived value / proposal / assumption / pending confirmation
```

Use JSON Pointer for case-derived fields; identify the original file/hash and relevant original value. For PDFs give PDF page number, section/table/figure, and short supporting text where readable. Distinguish source-reported findings, organizer's prospective contracts, calculations, and planning proposals. Preserve contradictory evidence rather than voting by citation count.

Read [references/methodology.md](references/methodology.md) to operationalize hypotheses, variables, comparisons, experimental units, controls, measurements, sample/reagent quantities, and decision criteria. **Freeze a concise primary-analysis specification before detailed cost optimization**: target estimand, source-supported/conditional metric definitions, occasion-to-observation-to-experimental-unit aggregation, directional transformations, analysis model, and decision rules. For repeated observations, specify whether aggregation precedes a transformation and its order relative to the primary contrast. Distinguish a genuine bounded zero, unmeasurable response caused by loss/death, ordinary missingness, and below-limit data; give an informative-zero/omission consequence and an allowed sensitivity analysis rather than an epsilon or silent complete-case removal. If the source does not supply the complete algebra, do not call a convenient proposal a recovered original estimator: label it conditional and say precisely what remains unfrozen. Only use power with supported model, independent unit, meaningful effect, variance, alpha, and target power; otherwise leave precision/power unknown or provide a labeled sensitivity analysis.

### 3. Compare and revise all source candidates

**Before ranking, verify planned demand and causally valid ordering.** Separate offered services from the candidate's actual requested `step → service/material/sample` edges; keep required QC, but exclude unrequested modalities/isolate-dependent analyses from formulas and bookings. Check identity/calibration/release gates against their dependent task and actual interval, with an explicit interpretation of ambiguous timing language. Cross-tabulate configuration against date/block and state whether the contrast is identified; a common block does not by itself remove configuration–day confounding or supply a covariance model. Recompute all costs and quotas for the declared recalibration fallback, rather than assuming spare capacity. A schema or resource pass cannot cure an unowned prerequisite or an invalid scientific contrast.

First normalize each original candidate separately into `/app/work/candidates/<id>.json`. Preserve the supplied hypothesis, steps, controls, run counts, and original resource/schedule terms without silently repairing them. Compare like-for-like and retain unsuitable originals with reasons, not only the preferred plan.

Translate only source-supported aspects into `/app/work/plan-audit.json`, following [references/audit-format.md](references/audit-format.md) and [schemas/plan-audit.schema.json](schemas/plan-audit.schema.json). Include independently traceable parameter domains, quantity/cost breakdowns, scientific checks, activity dependencies, and declared resource windows. Do not invent values merely to make this internal representation complete. Keep unrepresentable scientific or calendar constraints in explicit review issues.

Audit without claiming completeness of a search:

```bash
python3 "$SKILL_ROOT/scripts/plan_audit.py" audit \
  --input /app/work/plan-audit.json --case /input/case.json \
  --source-root /input --output /app/output/validation.json
```

Use the case-derived expected candidate count when known. Add `--expected-candidates N` only when N came from the case; add `--exhaustive` only if every listed discrete parameter domain is actually enumerable and the complete Cartesian coverage is required. Never interpret a search limit or a heuristic schedule as proof of infeasibility or global optimality.

Also request `--summary-output /app/output/audit-summary.json` and inspect that before opening large detailed reports. Normalize the case once per candidate; do not repeatedly translate it or re-read all of `plan_audit.py` and all source text to recover arguments or routine fields. Use the helpers' `--help`, these references, targeted evidence pages and compact summaries. If a candidate structure is unsupported, record that boundary rather than creating fictitious parity with the helper schema.

Revise only based on an actual validation issue or case-supported scientific improvement. A candidate may legitimately remain unchanged. If making a baseline → repaired/feasible → selected/reviewed progression is useful, retain each version's original lineage; do not pretend supplied sibling candidates are a linear history.

After every change:

1. Save that complete candidate and re-audit **all** affected scientific checks, quantities, domains, costs, and schedules.
2. Reject changes that create more severe scientific deficits or unresolved hard constraints, even if cheaper.
3. Generate and replay the revision record; keep the original raw files unchanged:

```bash
python3 "$SKILL_ROOT/scripts/case_io.py" diff \
  --before /app/work/candidates/before.json \
  --after /app/work/candidates/revised.json \
  --output /app/work/change.json
python3 "$SKILL_ROOT/scripts/case_io.py" verify-diff --change /app/work/change.json
```

Use at most **two focused correction rounds**. The second round addresses concrete residual issues; it is not a generic request for the model to praise itself. Preserve failed trials in the run record. At the end of a correction round, save the usable result before attempting any optional improvement. If no feasible candidate is found, report the searched coverage, precise conflicts, and which constraint relaxation needs expert approval.

**Selection and schedule discipline.** Do not turn uncertainty about a future response or unavailable power inputs into an automatic refusal to recommend. Where the case permits, explicitly recommend or rank a **provisional, source-supported plan** with exact conditions and scope, rather than rejecting every useful candidate or declaring unconditional optimality. A missing power input is a blocker when the requested decision actually needs a power/precision threshold; it must not silently justify an unsupported threshold. Scientific non-identifiability, forbidden parameter/resource conditions, incompatible controls, or missing evidence essential to the primary question can make a candidate ineligible; routine future uncertainty alone cannot. If none can answer the primary question, leave selection null and specify the exact additional fact/resource that would change that decision—not an invented trial outcome. Every meaningful uncertainty needs its decision impact and next check, not a generic expert role or endless refinement.

**Budget the context, not just CPU.** Reuse normalized evidence and shared constraints by stable IDs; avoid repeating literal source transformations. Preserve shared source values, units, prices, and calendars once using the `defaults` mechanism in [references/audit-format.md](references/audit-format.md), then override only actual candidate differences. Never change a measured scalar while retaining the old source or inherit positive resource units into an explicitly zero-demand task. Keep the zero quantity in its proper cost/quantity scope; do not create an invalid `units: 0` request merely to preserve a schedule entry. Do not mark every fee `capacity` to erase its cost; use `none` only for source-confirmed gross pricing with no stock rule. Call `python3 "$SKILL_ROOT/scripts/run_clock.py" check --work /app/work` before any optional expansion or correction. When its elapsed time reaches 600 seconds, stop new subordinate searches and preserve the complete conditional plan already supported; then validate and freeze. Never reread entire large reports for routine edits: use bounded projections of actual issues, budget, capacity, horizon, and status, and use the detailed report only for a targeted question. This clock is a lower bound from the first helper invocation, not an official model runtime or a replacement for final platform trace accounting. **Respect the task's per-response token limit, including reasoning.** Keep each model turn comfortably below that limit: split large result/generator writes by candidate and section, avoid serializing every candidate and the entire evidence ledger again in one oversized tool call, and shorten deliberation before an oversized write. Use small, incremental valid files and optionally permitted sidecars, rather than dropping required facts or violating the contract. Use native traces to check the actual response token count; file size and helper CPU time are not token or total-runtime measurements.

### 4. Review meaning, not just calculations

Read [references/risk-review.md](references/risk-review.md). For every material failure path, give its observable trigger and source of the criterion, protection/stop proposal, bounded diagnosis, repeat/resource limit, allowed interpretation, candidate-specific fallback, and resumption/review owner. A failed positive control is not evidence of no biological effect; a valid non-detect is not zero effect.

Prioritize the original contract, every source candidate, scientific hard gates, and quantity/schedule verification before material risk cards. Reuse shared failure mechanisms across steps/candidates instead of copying full templates. Expand minor risks only after saving complete usable artifacts; missing time leaves honest `not_run/unknown` records, not empty template claims. Proportional review must not remove a case-required risk, a significant safety/governance concern, or a primary scientific failure path—it removes repetition, not coverage.

Check the following in the actual sources and proposed plans:

- The intervention/comparison, target scope, operational variables, and outcome criteria are coherent. Avoid importing clinical or biological terminology where it does not fit.
- Independent experimental units are not replaced by technical observations; treatment and batch are not inseparably confounded. Nested vial/individual/readout counts do not create independently plumbed treatment loops. If only one physical loop exists per treatment, preserve that inference limit. Proposed randomization/blinding is not reported as executed.
- Controls address identifiable alternative explanations; analytical QC and scientific comparison groups are distinct. Where relevant, require blind image/SEM/indentation evaluation to both family and treatment, and prohibit specimen-order leakage. When two scorers are used, preserve individual skills/responsibility and consensus separately from experimental-unit counts.
- All claimed instruments/materials, ranges, input quantities, prices, and time windows are source-supported, correctly dimensioned, and included in the run-level accounting. Capacity caps/lot limits are distinct from deductible procurement inventory and from actual availability. Map them accurately and assess ability versus price separately.
- Arithmetic/domain/schedule success is not mislabeled scientific applicability, safe residual risk, equivalence of substitutes, or human approval. Attribute any directional or inverse transformation clearly to its source or proposed ratio/definition—not its memory of a familiar-looking variable.
- Every material output claim has an appropriate source or clear proposal/assumption label. Every necessary safety, ethics, statistics, domain, equipment, or procurement confirmation has a responsible role. Do not turn every routine method into an approval blocker; proportional review fits the actual decision.
- In a change narrative, include changed quantities, experimental-unit hierarchy, familial relatedness/cross-map, resource consumption, prices, calendar, and scientific scope. Changing dam usage or matching cohorts is not “everything else unchanged,” even when quoted costs are unchanged. Derive comparison/status fields from the same auditable per-version snapshot instead of writing conflicting booleans in different sections. Keep original and revised verdicts distinct by explicit scope.

### 5. Publish truthful artifacts and freeze

Write `/app/output/result.json` first in the **original contract**, including its literal `case_id` and every required field. Where the contract permits, include `status`, `sources`, `uncertainty`, and `change_records`; otherwise honor the original type/additional-field rules and place the remaining evidence in referenced sidecars. Return results in the task's language. Preserve source context and units.

Also retain a concise human-readable `plan.md`, the real `validation.json`, source/contract inventory, candidate snapshots, and `run_record.json` with actual (not aspirational) tool actions, errors, versions, times, input/output hashes, correction rounds, and `not_run` checks. Do not fabricate model usage, benchmark scores, or unavailable provenance. Office/slide/diagram artifacts and real PDF/PNG previews are needed only if the case requests them.

Before finishing, run:

```bash
python3 "$SKILL_ROOT/scripts/case_io.py" validate \
  --case /input/case.json --result /app/output/result.json \
  --output /app/output/contract-validation.json
python3 "$SKILL_ROOT/scripts/plan_audit.py" audit \
  --input /app/work/plan-audit.json --case /input/case.json \
  --source-root /input --output /app/output/validation.json
```

Repair actual findings, then re-run the checks. Preserve a known-valid partial if a new update fails. A returned status of complete describes generation coverage only; it cannot make an unresolved scientific/resource/expert gate disappear. For unsupported contracts or calculations, state `not_run` and why.

## Resources and boundaries

- Python 3.9+ standard library; no network, account, personal file, or external solver dependency.
- [references/usage.md](references/usage.md): invocation and clearly marked synthetic example.
- [references/audit-format.md](references/audit-format.md): normalized internal audit input, not the case output schema.
- [references/references.md](references/references.md): methodological background, never a substitute for case-specific evidence.
- [README.md](README.md): installation, maintenance, limitations, and self-check commands.

This skill supports document-based scientific planning, comparison, and revision. It does not perform an experiment, replace laboratory SOPs or safety/ethics review, establish reagent equivalence, reserve instruments, or predict unmeasured responses. Keep the first useful partial by about 90 seconds, the main candidate analysis by 600 seconds, and a final review margin before 900 seconds. When less time remains, prefer complete, truthful contract-preserving artifacts over unexplained expansion.
