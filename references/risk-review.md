# Risk review for source-bound experiment plans

Use this reference after a candidate has a defined question, unit hierarchy, run table, and resource calculation. For each candidate, identify failure paths that could change scientific interpretation, safety/governance, resource feasibility, or candidate selection. Reuse one `failure_id` for the same failure mechanism and map the affected steps/candidates with actual differences; do not mechanically expand the full step × failure-mode Cartesian product. A generic hazard list is not a review. All interventions below are proposals for responsible personnel, not actions the planner has performed.

## 1. Keep status dimensions separate

Never use a successful script, scientific review, or scenario-feasible budget as evidence of another dimension. Use the actual `output_contract` enums unchanged. The meanings below guide mapping; emit new labels only in fields whose contract permits them.

| Dimension | What must be established | What it must not imply |
|---|---|---|
| Generation completeness | All required fields/candidates are present, or omissions and limits are explicit | Scientific adequacy or permission to execute |
| Scientific readiness | Question, units, controls, measurement fit, design, thresholds, and alternatives are justified; unresolved scientific holds remain visible | That a future result will support the hypothesis |
| Runtime integrity | Inputs were parsed; helpers ran; domain, arithmetic, calendar, and structure checks have traceable outcomes | That scientific assumptions, thresholds, or material equivalence are true |
| External review/approval | Applicable local review scope is determined and genuine records cover this exact version where required | A model-generated approval, exemption, reservation, or executed safety action |

Keep measurement outcomes separate as well: `invalid run`, `valid non-detect`, `out of range`, and `undetermined` are not approval statuses.

Do not collapse these conditions:

- **Missing input:** a required fact is absent; state its impact and what would resolve it. This is not proof of infeasibility.
- **Infeasible:** a fully specified rule plus known inputs proves a domain, resource, calendar, or design constraint is violated.
- **Tool/runtime error:** parsing, helper execution, or service operation failed; preserve the scientific assessment separately and save usable partial output.
- **Not applicable:** a justified reason shows the risk or field does not apply to this candidate. Unknown is not a reason for `N/A`.

## 2. Instantiate a bounded failure card

Use the following template directly. Populate only relevant fields, but retain required contract fields. Reference actual source locations rather than inserting customary numbers.

```yaml
failure_id: ""
candidate_version: ""
step_id: ""
function_and_failure_mode: ""
causes_to_test: []
effects: {scientific: "", validity: "", safety: "", resources: ""}
observable_trigger:
  metric: ""
  operator: ""
  lower_bound: null
  upper_bound: null
  unit: ""
  evaluation_window: ""
  threshold_and_bounds_source: ""
  measurement_or_domain_bounds: ""
  on_missing: "undetermined"
run_validity:
  affected_steps_batches_samples: []
  classification: "valid|invalid|undetermined|not_yet_measured"
  interpretation_stopped: ""
immediate_proposed_protection:
  action: ""
  scope: "affected branch only unless wider impact is demonstrated"
  proposed_actor: ""
  execution_claim: "proposed_not_executed"
diagnosis:
  ordered_checks: []
  observable_branch_rules: []
  max_extra_runs: null
  max_extra_samples: null
  max_extra_cost: null
  max_extra_time: null
  max_retries: null
  terminal_state_if_unresolved: "undetermined; escalate to owner"
interpretation:
  allowed: ""
  prohibited: ""
specific_alternative:
  candidate_or_version_id: null
  changed_fields: []
  evidence_all_changes_are_in_allowed_domains: ""
  scientific_objective_preserved_or_changed: ""
  new_or_changed_risks: []
revalidation_required:
  scientific_and_QC_checks: []
  full_domain_resource_calendar_replay: true
  external_change_review: ""
resume_criteria:
  objective_predicates: []
  required_record_or_decision: ""
human_owner: ""
provenance: []
```

The trigger must be observable and tied to a case source, device/SOP, validated method, or explicitly proposed rule awaiting the appropriate review. Record one- or two-sided bounds and units where applicable. A missing observation is undetermined, never a pass. Do not assign a numerical probability, severity score, or RPN without source; never let a score offset a critical control failure or missing mandatory approval.

## 3. Required failure-mode coverage

Instantiate only cards with a credible causal mechanism or a material effect on the primary conclusion, using each candidate's actual branches and limits. Clearly inapplicable categories can share one concise reason per candidate; do not generate per-step N/A templates. Do not use proportional review to remove an explicitly required risk, a significant safety/governance concern, or a primary scientific failure path. Follow the detection–isolation–recovery structure of [NASA GSFC-HDBK-8004](https://standards.nasa.gov/sites/default/files/standards/GSFC/Baseline/0/GSFC-HDBK-8004_Approved_1.pdf) without importing aerospace severity levels.

### Contamination or suspected contamination

- Trigger from the method-specific blank, negative, no-template, or cross-sample pattern and its sourced bounds; absent controls make validity undetermined. Preserve raw signals, labels, lot/workflow records, and affected scope.
- Propose pausing interpretation and affected processing only, with local containment or exposure procedures when indicated. Do not claim material isolated, decontaminated, or safe, and do not invent disinfectant conditions.
- Bound diagnosis across sampling, extraction/preparation, reagent and detection controls, shared consumables, positions, and batches. A proposed alternative must be an allowed, fit-for-purpose workflow or independent retained sample, not merely “change reagents.” Resume only after cause control, the defined QC checks, and any required local release.

### No signal, non-detect, or out-of-range result

- Separate missing raw data, invalid system suitability, below detection limit, below quantification limit, and above reportable range; each has different permitted interpretation and dilution/repeat rules.
- With all required controls valid and the method suitable, a valid non-detect means only “not detected under these conditions” or below the stated limit. It is not zero concentration or proof of zero effect.
- Diagnose raw acquisition and system suitability before sample integrity, process controls, and validated matrix interference. Cap repeats and extra sample use. Only an allowed method/device with evidence for the needed range and matrix is a specific alternative; extrapolation or repeated measurement until desired is not.

### Failed scientific control, assay control, or baseline/QC check

- A failed required positive, negative, internal, calibration, or system-suitability control makes the affected run or branch invalid or undetermined according to the prespecified rule. It is not a biological null or evidence that treatment failed.
- Propose suspending scientific interpretation for exactly the affected scope. Do not repair a failed control with arbitrary baseline subtraction, renormalization, curve deletion, or selective exclusion.
- Check control identity/preparation, raw response, calibration/maintenance, lots, trends, and sample-matrix effects in a bounded order. Resume after original acceptance criteria are met and affected performance has been revalidated; an orthogonal method must be justified and allowed.

### Device range, resolution, or method-performance mismatch

- Check units and distinguish intervention setting domain, device operating range, measured signal range, validated/reportable range, resolution, and uncertainty relative to the decision. Never silently clamp an out-of-domain setting.
- Propose holding the invalid parameter or measurement branch, not necessarily unrelated work. Preserve out-of-range data and identify whether the control variable or measured response failed.
- Recompute after unit conversion and verify calibration/validation coverage. Use only a listed compatible device, sample-handling route, or parameter version; assess partial/full method revalidation when the range changes. The device/method owner resolves the resource or performance hold.

### Insufficient reagent stock or independent samples

- Recompute inclusive demand: treatment EUs, scientific controls, QC, independent runs, resource-consuming observations, validated losses, and explicitly authorized reserves. Compare qualified stock to demand and delivery/expiry to the actual use window.
- Unknown stock, yield, specification, or delivery is missing input, not availability. Similar name or CAS alone does not establish reagent equivalence; substitution needs fit-for-purpose evidence, change review, new-risk review, and any revalidation.
- For samples, distinguish independent EUs from technical observations and account for planned exclusions. Do not consume scarce samples on an unbounded diagnostic path. A fallback must still answer the primary question at its defensible EU count; otherwise label the reduced scientific scope exploratory rather than retaining the original confirmatory claim. Apply required ethics amendment review for changed participant/animal use.

### Budget or booking conflict

- Recalculate every candidate under the same price, package, billing, control, and repeat rules. Show the exact driver when cost exceeds the scenario budget, the dependency finish exceeds its window, delivery misses the critical path, or exclusive resources overlap.
- Missing price, currency/tax treatment, duration, or window means indeterminate, not free or booked. Proposed holds and resumed work consume no real resources.
- Remove only items explicitly optional for the primary goal, or select a named allowed candidate that survives full scientific and resource replay. Do not delete mandatory controls, safety measures, independent EUs, or unreported repeats to fit constraints. If no candidate survives, report no feasible candidate rather than inventing one.
- Prices and calendars are organizer scenario contracts, not vendor quotes or real reservations. Planning language must remain `calculated`, `proposed`, or `scenario-feasible`, never `purchased` or `booked`.

### Safety, ethics, privacy, and other governance

- Identify activity-specific hazards, exposure/release paths, waste, vulnerable subjects/data, transport, facility rules, and the current protocol/version scope from actual sources. “Wear PPE” is not a risk assessment.
- Propose an immediate stop/Isolation only within the credible affected scope for a defined event; actual emergency and incident procedures belong to local authorized personnel. Never provide unsupported neutralization, decontamination, or exposure-treatment instructions.
- Where approval applicability is undetermined, absent, suspended, expired, or does not cover the changed version, keep research implementation outside the authorized claim. Do not self-declare exemption or infer approval from a similar project. Only a valid external record from the authorized body can clear an actual approval hold.
- Use local, proportionate assessment as described by the [WHO Laboratory Biosafety Handbook, fourth edition](https://www.who.int/publications/i/item/9789240011311). Human, animal, privacy, biosafety, chemical, radiation, and other reviews apply according to jurisdiction and activity; no single committee name is universal.

## 4. Make the review proportional and closed-loop

- Do not attach `expert pending` to every routine low-risk proposal. Work within established sourced methods and known low hazards may remain a clearly labelled plan for the responsible experimenter, with ordinary local checks and documented assumptions; this does not authorize work outside existing approvals or competency.
- Require targeted domain/method review for uncertain construct validity, control interpretation, material equivalence, or a changed primary objective; statistics review for uncertain EU structure, complex designs, sample-size/model assumptions, or resource-driven inferential changes; device/metrology review for range and calibration substitutions.
- Require the applicable quality, EHS, ethics/privacy, or other authorized review for new/significant hazards, incidents, scope changes, regulated subjects/materials/data, or changed validated conditions. Routine narrative completeness is not a reason to invent an external-review requirement.
- Following [ICH Q9(R1), §§4–5](https://database.ich.org/sites/default/files/ICH_Q9%28R1%29_Guideline_Step4_2022_1219.pdf), record controls, residual-risk decisions, communication, and review. Check whether a fallback introduces new risks; scarce resources do not justify weakening risk control.
- A single QC improvement cannot clear an unrelated safety, ethics, or scope hold. Conversely, a local failure should not automatically invalidate unaffected branches without evidence of shared exposure or cause.
- After every fallback or correction, replay all finite-domain, inclusive resource, capacity, calendar, risk, and output checks; retain parent/version diffs and changed approval scope. Limit externally motivated correction rounds to two and end unresolved diagnoses as undetermined with an owner rather than retrying indefinitely.
- Deterministic checks can establish internal consistency, arithmetic, and contract compliance only. They cannot establish scientific threshold validity, equivalence, hazard elimination, actual booking, or approval authenticity.

## 5. Capacity, purchasable stock, and actual availability

Keep these judgments separate even when they share the same numeric table:

- **Capacity** is an upper bound for scenario demand. A capacity count is not an existing, charge-free procurement inventory; it neither authorizes unlimited use nor lets you leave out plannable specification/compatibility checks.
- **Deductible owned stock** is distinct material available under a source-declared purchase rule. A deduction is never a generic way to make a plan cheaper. Package rounding applies only to the shortage being purchased, not to the entire required quantity when the shortage is what must be procured.
- **Per-use charges and availability** are not identical. A known gross price can coexist with unverified real availability, an unknown capacity, or an approval hold. Never replace an unavailable physical resource with a lower quoted number, an assumed zero-cost replacement, or a claim of confirmed supply.
- Each candidate needs its own source-typed quantity, unit, cost owner, capacity, provenance and local hold status rather than combined stock or a budget-minus narrative shared across candidates.

Always preserve the three-way distinction: **planned is not executed; executed is not necessarily valid; neither planned nor executed is expert approved**. Release only the status supported by genuine evidence and external records, with unresolved limits and owners explicit.
