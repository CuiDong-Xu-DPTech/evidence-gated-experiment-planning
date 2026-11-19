# Declared state-consistency checks

`scripts/state_consistency.py` is a small **semantic consistency checker**, not a grader or a scientific validator. It compares only the current JSON values at pointers explicitly declared to represent the same case, version, semantic event, and state. It never decides that a source supports a claim, a booking exists, a resource is actually available, or science/safety/expert approval has been granted.

## Invocation

From any working directory, call the installed script by its actual path:

```bash
python3 scripts/state_consistency.py \
  --input /app/output/result.json \
  --rules /app/work/state-rules.json \
  --output /app/work/state-audit.json
```

The command reads existing UTF-8 strict JSON through `runtime.read_json`, does not modify either input, and writes the completed audit through `runtime.write_json_atomic`. The output path must differ from both input paths. Python 3.9 standard library plus the adjacent existing `runtime.py` is sufficient; no package installation, network access, or external command is used.

Exit codes are deliberate:

| Exit | Meaning |
|---|---|
| `0` | Every rule and comparison ran and was `consistent`; top-level `complete` is `true`. Repeated identical values are valid replicated observations. |
| `2` | An audit was written, but at least one rule is `inconsistent`, `different_scopes`, or `not_run`; top-level `complete` is `false`. |
| `1` | Structural/IO/rules-format failure: unreadable or invalid JSON, a non-object input root, empty/malformed rule bundle, duplicate rule IDs or declared pointers, too few paths, or output write failure. Structural failures do not silently produce a passing audit. |

The CLI prints a one-line summary. Importable helpers are `validate_rules(bundle)`, `audit_rule(document, validated_rule)`, and `audit_document(document, rules_bundle)`; `json_type(value)` exposes the six JSON type names used by comparison.

## Rules

A rules file is an object with a non-empty `rules` array. Each rule has exactly these supported fields:

- `id`: required non-empty unique string.
- `paths`: required array of at least two unique RFC 6901-style pointer strings. The user, not the script, establishes that their values have the same meaning.
- `scope_paths`: optional; omit it, use `[]`, or provide exactly one pointer per `paths` entry. These pointers locate the corresponding scope labels.
- `allow_different_scopes`: optional boolean, default `false`.

`examples/state-rules.example.json` is explicitly synthetic. It declares possible interfaces; it supplies no real case answer and does not imply that every document has those fields. Separate rules can compare separate semantics—for example, total cost in one rule and resource verdicts in another. The script does not infer such relationships on its own.

Pointers start at the input root. Use object keys and canonical zero-based array indices, escaping `~` as `~0` and `/` as `~1`. An empty pointer selects the root. Invalid escapes, missing keys, invalid/out-of-range indices, and traversal through null/boolean/number/string values do not resolve. A missing key is an error even when a neighbouring key happens to contain useful text.

### Exact `$ID` candidate association

`$ID` may replace exactly one path segment; no other wildcard or expression language exists. Every rule using it must have a `/candidates/$ID/...` anchor in `paths` or `scope_paths`. The root `candidates` array drives comparison in its existing order; IDs are never alphabetized or assumed to be alpha/beta/gamma. Within a candidate object, the first present field in `candidate_id`, `version_id`, `id` supplies the non-empty string identifier.

For another dynamic path, the static prefix before `$ID` must resolve to an array. The checker indexes that array's **objects with candidate identifiers**, then substitutes the exact index belonging to the root candidate's ID. It does not search field values or substrings. Unlabelled objects and non-object entries in such a satellite array are skipped, so an independent aggregate report can coexist with per-version records. All root candidate entries must be identified objects. A requested root ID missing from a satellite array, an invalid ID, a duplicate ID in any indexed array, or a missing/non-array prefix makes the affected comparison `not_run`.

Satellite entries whose IDs do not occur in root `candidates` are outside the dynamic comparison. For those versions, declare an explicit static rule or add the actual root candidate record; extras are never silently treated as current candidates. Two declared pointers that resolve to the same concrete pointer after substitution are also a `duplicate_pointer` error, not a reason to deduplicate the comparison.

A static rule has one comparison with `candidate_id: null`. A dynamic rule emits one comparison per root candidate; its `candidate_id` is the matched string even when the source field was `version_id` or `id`.

## Value and scope semantics

Values are retained as JSON, not stringified or truthiness-coerced. All compared values must have one JSON type: `null`, `boolean`, `number`, `string`, `array`, or `object`. A type mismatch is `not_run/value_type_mismatch`, so `true` versus `"true"`, `1` versus `"1"`, and `null` versus `[]` can never be read as agreement. Numeric values share the JSON number type (`1` and `1.0` have equal numeric value); booleans are never numbers. Arrays compare full length and values in their existing order. Objects compare their complete key/value content; object key display order is not semantic, and no array is sorted.

`scope_paths`, when present, must resolve to explicit labels only: non-null JSON scalars, with non-empty strings and one shared JSON type. Null, arrays, objects, empty strings, mixed label types, and unresolved labels yield `not_run/scope_type_or_shape_invalid` or a pointer error. Labels are shown beside each corresponding value.

- Different scoped values plus distinct valid labels yield `different_scopes/distinct_scopes` **only** when `allow_different_scopes` is `true`. This preserves a before/repair difference without calling it same-state agreement; it is not an overall pass.
- With the default `false`, any distinct scopes are visible as `inconsistent/scope_mismatch`, even if the verdict values happen to be equal. Without scope labels, differing same-type values are `inconsistent/value_mismatch`.
- Equal values with no forbidden scope mismatch are `consistent`. Supplying multiple truth values is never required for a valid consistency result.
- Enabling `allow_different_scopes` without providing distinguishing labels cannot excuse different values: they remain `inconsistent`.

A scope label belongs to the rule's model. A field named `as_written`, `revised`, `supplied`, or `after...` does not by itself prove that two complete plans agree or describe the same event. In particular, `as_written=false` as a verdict is not a historical scope label and must not be promoted to one. Keep raw history in the input and point separately at its value and explicit scope.

## Audit and failure interpretation

The output has `schema_version`, copied `case_id` (or null), top-level `status`, `complete`, a summary with per-status **rule** counts and total comparisons, and per-rule verdicts. Each comparison contains its resolved `candidate_id`, ordered observations (`path`, original `value`, and scope data when configured), plus errors/issues. All competing current pointers and values remain visible rather than collapsing to a selected `true`.

Overall precedence is `inconsistent`, then `not_run`, then `different_scopes`, then `consistent`; detailed lower-severity findings remain in every rule. Only all-consistent audits have `complete: true`. `complete` here means declared pointer comparison coverage, not experiment completion, contract compliance, scientific correctness, or approval.

Pointer lookup failures, invalid scopes and duplicate concrete pointers make that comparison `not_run`; a driver failure makes that rule `not_run`. Known conflicts in other comparisons remain visible. This helper does not repair inconsistent fields, infer which value should win, merge candidate versions, or convert unknown/null/false into a passing fact. Review the exact candidate, paths, values, and scope labels before changing the authoritative document, then rerun the same real input.
