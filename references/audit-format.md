# Internal audit representation

This document describes `plan-audit.json`, an optional **working representation** for deterministic checks. It is not a replacement for the original `output_contract`; retain any scientific detail that cannot be represented honestly in the main result and evidence ledger.

```json
{
  "schema_version": "weekly-skill.plan-audit/v1",
  "case_id": "copy-from-actual-case",
  "source_registry": {},
  "candidates": [
    {
      "candidate_id": "source-candidate-id",
      "parent_id": null,
      "parameters": [],
      "cost_items": [],
      "tasks": [],
      "resource_calendars": [],
      "scientific_checks": [],
      "metrics": {},
      "budget_minor": null,
      "horizon_minutes": null
    }
  ],
  "priority": []
}
```

See `schemas/plan-audit.schema.json` for the authoritative normalized field types and `examples/audit.example.json` for an explicitly synthetic three-candidate interface example.

## Optional compact `defaults`

A top-level `defaults` object can hold candidate-level fields and any of the five repeated arrays. It is an input-only compact notation for repeated prices, parameters, task details, and calendars—not a science or availability answer layer. For example, the resource calendar below is written once while each compact candidate supplies its own identity and other candidate-specific fields:

```json
{
  "defaults": {
    "budget_currency": "XCR",
    "resource_calendars": [
      {"resource_id": "shared-instrument", "capacity": "1", "available_intervals": [["0", "480"]]}
    ]
  },
  "candidates": [
    {"candidate_id": "candidate-a", "parent_id": null, "parameters": [], "cost_items": [], "tasks": [], "scientific_checks": []},
    {"candidate_id": "candidate-b", "parent_id": "candidate-a", "parameters": [], "cost_items": [], "tasks": [], "scientific_checks": []}
  ]
}
```

Every compact candidate still needs its own `candidate_id`. Candidate-owned fields other than the five arrays replace the same default field, including an explicit `null`; in particular, `parent_id: null` is not dropped or replaced by a truthy default. When `defaults` is absent, the original complete-candidate schema and behavior are unchanged.

The arrays merge by `name` (`parameters`), `id` (`cost_items`, `tasks`, `scientific_checks`), or `resource_id` (`resource_calendars`). **Every override entry must repeat its stable key** (`id`, `name`, or `resource_id`) so it can identify the intended default row; do not remove that key merely because it is duplicated in the shared record. An override without its key is not matched by position and cannot borrow the corresponding default identity. Normal field validation reports incomplete entries. Defaults retain their order and genuinely new candidate keys with complete records append in candidate order. A top-level candidate array is therefore a set of patches/additions, not a wholesale replacement: `tasks: []` does not delete default tasks. Duplicate default keys are structural errors with `/defaults/...` paths. Repeated candidate keys are retained for the normal duplicate audits rather than collapsed into one winning entry. If a shared value or its source is ambiguous, keep the full per-candidate record rather than forcing compression.

A matching entry is copied, then its candidate-owned fields replace default fields one level down. Object and array values are not deep-merged or concatenated. Thus `resources`, `domain`, `affected_steps`, and `available_intervals` replace the inherited value as a whole, including an intentional empty array, while array-valued fields absent from the patch remain inherited exactly. Supplying `source` on a patch likewise replaces the entire source object; it does not inherit only `file`, `pointer`, or `raw` from the default source.

**Source-overwrite rule:** when a patch actually changes an inherited source-backed value, it must also supply a complete source object on that candidate entry. This fail-closed rule covers:

- parameters: `value`, `domain`, `unit`;
- cost items: `quantity`, `unit`, `stock_role`, `stock_available`, `pack_size`, `unit_price_minor`, `currency`, `fixed_cost_minor`;
- tasks: `resources` (including nested `units`), `earliest_start`, `deadline`, `start`, `duration_minutes`;
- calendars: `available_intervals`, `capacity`.

Reasserting an identical value does not require a redundant source. Omitting the patch source, or supplying a non-object source, produces `DEFAULTS_SOURCE_REQUIRED`; an old default locator cannot silently stand behind a different candidate quantity, price, time, or calendar. A complete replacement source is otherwise permitted and receives the existing locator, exact raw-value/type, and integrity checks. It still does not establish semantic support or scientific correctness.

Calendars may declare `source` even without an override. Declared calendar sources are audited and counted with other sources, and appear under `schedule.calendar_sources`; unchanged legacy calendars are not forced to acquire one. Calendar source checks do not claim that a capacity or interval is actually available.

The full report contains a small `defaults_trace` only when `defaults` was present, recording merge/append counts and the applied policy. Expansion performs no network access, scientific inference, unit conversion, financial discount, or availability inference; all existing arithmetic, scheduling, parent-link, and failure checks run on the expanded candidates.

## Parameters

Each parameter preserves its stable name, numeric string or categorical value, unit, and actual domain:

- `domain: [allowed values]` for discrete enumerations.
- `domain: {min, max, step, origin, unit}` only when that interval and step came from the case. Bounds are checked exactly with rational arithmetic; do not add a midpoint or a step merely to obtain an answer.
- `source`: file plus RFC 6901 pointer for case JSON, or real PDF document plus page/section/table locator. Include the raw input value where useful.
- `normalization`: any conversion actually used, with factor/unit and its source. A script cannot validate an unstated dimension conversion; unresolved unit ambiguity stays unknown.

`source_registry` is an object mapping stable artifact IDs to real metadata `{file, sha256?, media_type?}`, not an array. For a `source` entry, `raw` is the exact JSON value **and its original JSON type** at that pointer, not the `str()` of that value. For example, an original number `51` must not be described as the string `"51"`; a normalized numeric string or categorical value belongs in the parameter/cost field, separate from `source.raw`. Preserve original bytes/hashes and pointers rather than changing a field into the shape that is easiest to compute.

Never clamp an out-of-domain choice. A source locator/hash validates attachment to a record, not the scientific interpretation or applicability of that record.

## Cost lines: capacity is not purchase inventory

Each cost item identifies its total **quantity for this candidate**, unit, supported billing rule, unit price in minor currency units, currency, and source. Aggregate quantities from the actual run table, including required controls, QC, and specified repetitions; the script intentionally does not infer scientific replication.

Use the optional `stock_role` to keep two meanings separate:

- **`capacity`**: `stock_available` is an availability limit, not free procurement. The price applies to all required quantity. With explicit pack size, use `ceil(quantity / pack_size)` rather than deducting capacity first. Check `quantity <= capacity` and report overflow/margin; an overflow is a capacity failure, not something to clamp. If capacity is missing, availability remains pending—do not invent an empty or unlimited stock. Gross fees and availability are separate judgments.
- **`purchase`**: only where the actual contract explicitly describes owned stock available for a purchase-cost offset. Then the previous net-procurement calculation applies.
- **`none`**: only when the case explicitly defines gross consumption pricing with no stock rule for this item. Full quantity is billed, including any explicit pack increment. `stock_status` and `deficit_status` are `not_applicable` in this specific role—not unknown and not proof-of-available-stock. Absence of this stock rule does not mark known per-use prices incomplete, while missing prices, quantities, fixed charges or evidence remain pending separately. This says nothing about real availability and cannot be used with a supplied `stock_available`; distinguish a genuinely absent rule from an omitted input.
- **Unspecified `stock_role`**: retains the legacy behavior and explicit uncertainty. Never infer discounts or ownership from a field called `capacity`, a dataset row, or a plausible resource name. Do not mark every item `capacity` to erase charges, nor `none` to erase a documented limit.

For a purchase, with known quantity `q`, deductible owned stock `s`, and explicit pack size `p`:

```text
shortfall = max(0, q - s)
packs = ceiling(shortfall / p)
billed_quantity = packs × p
item_cost_minor = billed_quantity × unit_price_minor
```

If stock/ownership is unknown, do not choose free or zero stock: retain gross-cost and procurement/capacity uncertainty separately. If no pack rule exists, use only the source-supported billing rule. Total same-currency minor units exactly and compare against the declared budget without display-stage rounding. Missing price, incompatible currencies, and unknown quantity/billing rules block complete cost verification; they are not zero charges. Do not use a capacity value to turn per-use charges into a false discount.

For large reports, also request `--summary-output /app/output/audit-summary.json`. Its schema is `weekly-skill.plan-audit/v2.summary`; `full_report_schema` identifies the independent full ledger used for comparison. The v2 summary is serialized as compact one-line JSON to reduce navigation size without changing the full report's formatting or status.

The v2 capacity records replace verbose names with `quantity`, `unit`, `capacity`, `margin`, `status`, `billed`, `cost_minor`, and `cost_status`; same-currency totals and declared comparisons remain in `cost.currencies` and `cost.declared_comparisons`. The repeated margin-basis prose is available only in the full report. A passing item source is represented by `source:"pass"`. Any capacity, cost, or source anomaly keeps `anomaly:true` plus the available file/locator/raw/integrity details, and exact `/candidates/.../source/...` paths remain under the candidate issues.

Candidate pending conditions remain in `machine_issues` or `other_issues`; the summary does not repeat them in per-candidate `pending_inputs`, nor duplicate non-pass scientific details in `pending_experts`. Top-level `pending_inputs` contains only input/search/ranking issues, so each candidate issue still provides precise candidate/path navigation. Schedule entries whose explicit severity is `info`, including project-horizon provenance, are omitted as non-conflicts; `fail` and `unknown` entries retain severity, code, path, and message. The summary copies actual report/candidate statuses and never turns an unknown, source failure, intentional candidate failure, or safety/science review into approval or complete evidence.

## Activities and calendars

Tasks contain stable IDs, non-negative `duration_minutes` as numeric strings, predecessor IDs, needed resources, and source-supported release/deadline constraints when known:

```json
{
  "id": "source-activity",
  "duration_minutes": "30",
  "predecessors": ["preparation"],
  "resources": [{"resource_id": "instrument-a", "units": "1"}],
  "earliest_start": "0",
  "deadline": "480"
}
```

Calendars use `{resource_id, capacity, available_intervals:[[start,end],...]}`. Use half-open intervals; an adjacent task may begin exactly when the previous ends. A busy interval is removed from the provided availability upstream only if that is how the source contract describes it. No available interval on record means availability unknown, not unlimited. An interruptible activity or alternate equipment pool is supported only when explicitly allowed; otherwise flag it for review.

All numeric time endpoints use the same minute origin; ISO timestamps require timezone information and are normalized to UTC. Keep both the original time window and mapping in the human plan. A schedule produced by the helper is prospective and heuristic, not actual booking or a globally optimal assignment. Unknown calendars, resource capacity, duration, or deadlines are not successful checks.

`horizon_minutes` is the latest allowed task-end offset in that shared numeric origin, used when the case gives a hard plan-wide completion limit: every task must end at or before it. The audit compares exact end values and reports `HORIZON_EXCEEDED`; it does not force an ISO timestamp into an arbitrary numeric origin. When one case-supported plan-wide completion deadline applies to every included activity, tasks without individual deadlines inherit it with the explicit `candidate.horizon_minutes` provenance marker. Do not invent task-specific deadlines or turn a soft elapsed target into a hard limit. Use explicit absolute per-task deadlines for real calendar dates.

## Scientific checks and selection

`scientific_checks` records actual review judgments with `id`, `status`, `claim`, `source`, `reason`, and any expert/affected-step scope. Status is `pass`, `fail`, `unknown`, or `not_applicable`; not-applicable needs a reason. These judgments are not inferred by counting fields. A numerical report has separate `machine_pass` from scientific readiness or approval.

Use `--expected-candidates N` only for a count read from the actual case. `--exhaustive` explicitly checks the full Cartesian parameter-domain coverage within the specified search bound; otherwise the report records incomplete search coverage. If priorities are supplied, only declared numeric `metrics` and direction (`min` or `max`) are meaningful for comparison; unknown values are never zero. Scientific failures are not traded against cost/time, and arbitrary total scores are not invented.

## Parent lineage

A nonempty `parent_id` first resolves against supplied current candidates. If no current candidate has that ID, the auditor may resolve an original source candidate **only** from the `--case` document's `candidates` array, using a nonempty string `id`, `version_id`, or `candidate_id`. It never converts numeric IDs to strings. Each case entry supplies at most one match per ID; different case entries with the same parent ID are ambiguous.

A resolved parent remains unchanged in the full and v2 summary reports and gains `parent_reference`:

```json
{
  "parent_id": "original-version",
  "parent_reference": {
    "scope": "source_case",
    "path": "/actual/path/to/case.json",
    "pointer": "/candidates/0/id"
  }
}
```

Current references instead use `scope:"current_candidates"` and point to the actual audit input's `/candidates/N/candidate_id`. `parent_id:null` remains valid and needs no reference. An unknown parent produces `PARENT_CANDIDATE_MISSING`; duplicate current or source-case matches produce `PARENT_CANDIDATE_AMBIGUOUS`, and both fail the revised candidate rather than selecting a parent implicitly.

A source-case parent is lineage only. It does not add a candidate to `--expected-candidates`, create or merge a plan, import the original scientific verdict, or convert an original/current failure into a pass.

Read `validation.json` alongside the actual candidate plans and sources: arithmetic/domain/calendar validation does not verify citation entailment, correct controls, unit semantics, safety, or expert authorization.
