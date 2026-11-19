# Runtime and case-contract adapter

The submission ARM protocol and a case's `output_contract` are different contracts. Do not put ARM manifest fields into `result.json` or use a fixed research schema in place of the case contract.

## Inputs and files

- Evaluation input: `/input/case.json`, the actual task instruction (normally `/input/task.md`), and materials named by the case.
- Work: `/app/work`; case-independent intermediate representations and source extracts stay here.
- Results: `/app/output/result.json` plus truthful structured evidence files.
- The skill directory comes from its actual installation. Scripts use their own file location, never the process working directory.
- Inspect `/app/environment/resources.yaml`, `/input/environment/resources.yaml`, then `/app/work/environment/resources.yaml`. These are bounded alternatives, not an instruction to scan a host filesystem. If the manifest is unavailable, inspect only the tools actually invoked and record that fact.

The `case_io.py init` command discovers an unambiguous `output_contract` in the case. Supported forms include ordinary field mappings, field lists, and common JSON Schema-style properties. Nested or unfamiliar forms must be surfaced specifically rather than coerced into guessed fields. Every case-specified output field remains top-level unless the contract itself declares another structure. Copy the root `case_id` exactly; never substitute the challenge ID, filename, or an example ID.

For JSON Schema-style inputs, use the supplied types and required fields rather than generic placeholders. `case_io.py validate` checks common structural constructs locally. Advanced combinators, external references, and unrecognized DSLs are explicitly `not_run`/`unsupported`, not silently treated as valid. A type-less description still requires the agent to read its semantics; no fabricated type should be inferred merely from a field name.

`additionalProperties` may itself be a schema: for example, a resource-name → integer dictionary. Recursively validate the dynamic values; do not incorrectly refuse this standard construct merely because it is not a boolean.

An outer contract can carry an actual schema in `json_schema` plus artifact declarations such as `result_path`, `human_plan_path`, `validation_path`, `work_path`, and `run_record_path`. Only when at least two such path declarations are present does the adapter unwrap the inner schema and retain those artifact declarations as wrapper metadata in `contract_report.json`. They are not additional fields in `result.json`. Any separately required artifact must still be produced at the corresponding actual path. A plain required result field that happens to be named `json_schema` remains a result field and is never mistaken for wrapper metadata.

## Incremental and atomic output

1. Initialize the contract-guided partial result before resource-intensive work.
2. Stage the complete updated candidate JSON in work storage.
3. Use the scripts' atomic writer (or an equivalent flush and `os.replace`) to publish `result.json`, then read it back.
4. Keep the last known-valid partial if an update fails validation. Do not truncate JSON when time is scarce.
5. Append every actual change with its parent, affected pointers, reason, evidence, and revalidation outcome.

Intermediate null/empty values only indicate unfinished generation when permitted by the case's partial-status convention; they are not true scientific values. Do not fill a required boolean with `false` merely to pretend that a condition failed or was checked. Clear those placeholders as evidence becomes available, while retaining any unresolved uncertainty.

If the contract forbids extra keys, keep it authoritative. Put additional traceability in separate output files and reference them in an allowed field; do not violate `additionalProperties: false`. Existing contract fields named `status`, `sources`, `uncertainty`, or `change_records` retain their specified type and meaning. If there is no case-defined status, the internal generation vocabulary is `partial | complete | failed`; readiness is a separate judgment. A finished generation is not an authorized experiment.

## Evidence and change records

Each significant evidence entry should identify its kind (`source_reported`, `organizer_contract`, `candidate_plan`, `derived`, `plan_proposal`, or `assumption`), actual file, SHA-256 when available, precise locator, short relevant raw value, and intended use. A locator verifies where to look; it does not alone establish support for a broader claim. Derived values link to formula/input IDs and exact calculations. Assumptions link to impact and the review needed.

`source.raw` is the literal JSON value and original JSON type at its locator, not a stringified version of that value. Preserve original integers, booleans, arrays and objects alongside, not inside, their normalized parameter forms. Never silently turn `"51"` into `51` or `51` into `"51"` to make a schema fit. If a source lacks a value, record that absence or `null` according to the contract; do not invent a default.

Each revision uses authentic before/after files and JSON Patch-style operations. Save original-byte hashes, the base/parent relationship, and an operation-level replay result. Preserve step order and arrays with scientific meaning; do not reorder them to make a diff look neat. Original sources and candidates remain immutable in `/input` and work snapshots.

## Minimum run record

Record actual phase durations, real command invocations and tool versions when obtainable, source/input/output hashes, every validator invocation, issues found, corrections attempted, and skipped checks with reasons. Never manufacture external approvals, actual model usage, cost, time, or benchmark scores. Platform-owned native traces remain the evidence for model identity, repetitions, and budgets. Preserve service error/retry events and token usage with their actual scope and timestamps. Keep wall-clock span, paused service-failure intervals when the evaluator defines them, and output-token counts distinct; do not invent a generic downtime allowance or turn a proxy harness into an official DeepSeek Harness measurement. Split lengthy generation by candidate/section and leave response-token headroom for reasoning rather than fitting a giant serialized plan or generator into one turn.
