#!/usr/bin/env python3
"""Compare explicitly declared JSON fields without repairing their semantics."""

import argparse
import os
import sys

import runtime


SCHEMA_VERSION = "state-consistency/v1"
ID_FIELDS = ("candidate_id", "version_id", "id")
RULE_KEYS = {"id", "paths", "scope_paths", "allow_different_scopes"}
STATUSES = ("consistent", "inconsistent", "different_scopes", "not_run")


class RuleFormatError(ValueError):
    pass


class DataError(ValueError):
    def __init__(self, code, path, message):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_json(self):
        return {"code": self.code, "path": self.path, "message": self.message}


def json_type(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        return "number"
    if type(value) is str:
        return "string"
    if type(value) is list:
        return "array"
    if type(value) is dict:
        return "object"
    raise TypeError("value is not strict JSON")


def _decode_pointer(pointer):
    if type(pointer) is not str:
        raise RuleFormatError("pointer must be a string")
    try:
        tokens = runtime.json_pointer_tokens(pointer)
    except runtime.JsonPointerError as exc:
        raise RuleFormatError("invalid pointer %r: %s" % (pointer, exc)) from None
    if tokens.count("$ID") > 1:
        raise RuleFormatError("a pointer may contain at most one $ID segment: " + pointer)
    return tokens


def validate_rules(bundle):
    """Return validated rules; reject malformed bundles without deduplication."""
    if type(bundle) is not dict:
        raise RuleFormatError("rules document root must be an object")
    rules = bundle.get("rules")
    if type(rules) is not list or not rules:
        raise RuleFormatError("rules must be a non-empty array")
    seen_ids = set()
    validated = []
    for index, rule in enumerate(rules):
        location = "rules[%d]" % index
        if type(rule) is not dict:
            raise RuleFormatError(location + " must be an object")
        unknown = set(rule) - RULE_KEYS
        if unknown:
            raise RuleFormatError(
                "%s has unknown field(s): %s" % (location, ", ".join(sorted(unknown)))
            )
        rule_id = rule.get("id")
        if type(rule_id) is not str or not rule_id.strip():
            raise RuleFormatError(location + ".id must be a non-empty string")
        if rule_id in seen_ids:
            raise RuleFormatError("duplicate rule id " + rule_id)
        seen_ids.add(rule_id)
        paths = rule.get("paths")
        if type(paths) is not list or len(paths) < 2:
            raise RuleFormatError(rule_id + ".paths must contain at least two pointers")
        if any(type(path) is not str for path in paths):
            raise RuleFormatError(rule_id + ".paths entries must be strings")
        if len(set(paths)) != len(paths):
            raise RuleFormatError(rule_id + ".paths contains duplicate pointers")
        path_tokens = []
        for path in paths:
            try:
                path_tokens.append(_decode_pointer(path))
            except RuleFormatError as exc:
                raise RuleFormatError(rule_id + ": " + str(exc)) from None
        scope_paths = rule.get("scope_paths", [])
        if type(scope_paths) is not list:
            raise RuleFormatError(rule_id + ".scope_paths must be an array")
        if len(scope_paths) not in (0, len(paths)):
            raise RuleFormatError(
                rule_id + ".scope_paths must be empty or have one pointer per paths entry"
            )
        if any(type(path) is not str for path in scope_paths):
            raise RuleFormatError(rule_id + ".scope_paths entries must be strings")
        if len(set(scope_paths)) != len(scope_paths):
            raise RuleFormatError(rule_id + ".scope_paths contains duplicate pointers")
        scope_tokens = []
        for path in scope_paths:
            try:
                scope_tokens.append(_decode_pointer(path))
            except RuleFormatError as exc:
                raise RuleFormatError(rule_id + ": " + str(exc)) from None
        allowed = rule.get("allow_different_scopes", False)
        if type(allowed) is not bool:
            raise RuleFormatError(rule_id + ".allow_different_scopes must be boolean")
        dynamic_paths = [
            path for path in paths + scope_paths if "$ID" in _decode_pointer(path)
        ]
        if dynamic_paths and not any(
            tokens[:2] == ["candidates", "$ID"] for tokens in path_tokens + scope_tokens
        ):
            raise RuleFormatError(
                rule_id + ": each $ID rule needs a /candidates/$ID/... anchor"
            )
        validated.append({
            "id": rule_id,
            "paths": paths,
            "scope_paths": scope_paths,
            "allow_different_scopes": allowed,
            "dynamic": bool(dynamic_paths),
        })
    return validated


def _pointer_from_tokens(tokens):
    if not tokens:
        return ""
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)


def _lookup(document, pointer):
    try:
        return runtime.json_pointer_lookup(document, pointer)
    except runtime.JsonPointerError as exc:
        raise DataError("pointer_not_resolved", pointer, str(exc)) from None


def _record_id(record, array_path, index, required):
    location = "%s/%d" % (array_path, index)
    if type(record) is not dict:
        if required:
            raise DataError("candidate_not_object", location, "candidate entry must be an object")
        return None
    selected = None
    for field in ID_FIELDS:
        if field in record:
            selected = field
            break
    if selected is None:
        if required:
            raise DataError(
                "candidate_id_missing", location,
                "candidate needs candidate_id, version_id, or id",
            )
        return None
    value = record[selected]
    if type(value) is not str or not value:
        raise DataError(
            "candidate_id_invalid", location + "/" + selected,
            "candidate identifier must be a non-empty string",
        )
    return value


def _index_array(document, array_path, required):
    value = _lookup(document, array_path)
    if type(value) is not list:
        raise DataError(
            "identifier_array_expected", array_path,
            "the static prefix before $ID must resolve to an array",
        )
    if required and not value:
        raise DataError("candidates_empty", array_path, "candidates array must not be empty")
    indices = {}
    order = []
    for index, record in enumerate(value):
        candidate_id = _record_id(record, array_path, index, required)
        if candidate_id is None:
            continue
        if candidate_id in indices:
            raise DataError(
                "duplicate_candidate_id", "%s/%d" % (array_path, index),
                "duplicate candidate identifier %r in %s" % (candidate_id, array_path),
            )
        indices[candidate_id] = index
        order.append(candidate_id)
    return indices, order


class CandidateResolver:
    """Resolve $ID by exact identifiers, preserving root candidate array order."""

    def __init__(self, document):
        self.document = document
        self.indices = {}
        self.candidate_ids, self.order = _index_array(document, "/candidates", True)

    def resolve(self, pointer, candidate_id):
        tokens = _decode_pointer(pointer)
        if "$ID" not in tokens:
            return pointer, _lookup(self.document, pointer)
        position = tokens.index("$ID")
        prefix = tokens[:position]
        array_path = _pointer_from_tokens(prefix)
        if array_path not in self.indices:
            required = array_path == "/candidates"
            self.indices[array_path], unused_order = _index_array(
                self.document, array_path, required
            )
        index_by_id = self.indices[array_path]
        if candidate_id not in index_by_id:
            raise DataError(
                "candidate_id_not_found", array_path,
                "candidate %r has no exactly matching identified array entry" % candidate_id,
            )
        concrete_tokens = (
            prefix + [str(index_by_id[candidate_id])] + tokens[position + 1:]
        )
        concrete = _pointer_from_tokens(concrete_tokens)
        return concrete, _lookup(self.document, concrete)


def _static_or_dynamic(tokens):
    return "$ID" in tokens


def _rule_status(comparisons):
    statuses = [comparison["status"] for comparison in comparisons]
    if "inconsistent" in statuses:
        return "inconsistent"
    if "not_run" in statuses:
        return "not_run"
    if "different_scopes" in statuses:
        return "different_scopes"
    return "consistent"


def _compare_group(document, rule, candidate_id, resolver):
    observations = []
    errors = []
    concrete_paths = []
    for path in rule["paths"]:
        try:
            if resolver is None:
                concrete, value = path, _lookup(document, path)
            else:
                concrete, value = resolver.resolve(path, candidate_id)
        except DataError as exc:
            errors.append(exc.as_json())
            observations.append({"path": path, "error": exc.message})
            concrete_paths.append(None)
            continue
        if concrete in concrete_paths:
            error = DataError(
                "duplicate_pointer", concrete,
                "two paths resolve to the same concrete JSON pointer",
            )
            errors.append(error.as_json())
            observations.append({"path": concrete, "error": error.message})
            concrete_paths.append(None)
            continue
        concrete_paths.append(concrete)
        observations.append({"path": concrete, "value": value})
    if errors:
        return {
            "candidate_id": candidate_id,
            "status": "not_run",
            "complete": False,
            "observations": observations,
            "errors": errors,
        }

    for index, scope_path in enumerate(rule["scope_paths"]):
        try:
            if resolver is None:
                concrete, scope = scope_path, _lookup(document, scope_path)
            else:
                concrete, scope = resolver.resolve(scope_path, candidate_id)
            observations[index]["scope_path"] = concrete
            observations[index]["scope"] = scope
        except DataError as exc:
            errors.append(exc.as_json())
            observations[index]["scope_path"] = scope_path
            observations[index]["scope_error"] = exc.message
    if errors:
        status = "not_run"
        code = "scope_not_resolved"
    else:
        values = [item["value"] for item in observations]
        value_types = [json_type(value) for value in values]
        scopes = [item.get("scope") for item in observations]
        scope_types = [json_type(scope) for scope in scopes]
        invalid_scope = bool(rule["scope_paths"]) and any(
            scope is None or type(scope) in (list, dict)
            or (type(scope) is str and not scope)
            for scope in scopes
        )
        scopes_differ = any(
            not runtime.json_values_equal(scopes[0], scope) for scope in scopes[1:]
        ) if rule["scope_paths"] else False
        values_differ = any(
            not runtime.json_values_equal(values[0], value) for value in values[1:]
        )
        if len(set(value_types)) != 1:
            status = "not_run"
            code = "value_type_mismatch"
        elif invalid_scope or len(set(scope_types)) != 1:
            status = "not_run"
            code = "scope_type_or_shape_invalid"
        elif scopes_differ and not rule["allow_different_scopes"]:
            status = "inconsistent"
            code = "scope_mismatch"
        elif values_differ and scopes_differ:
            status = "different_scopes"
            code = "distinct_scopes"
        elif values_differ:
            status = "inconsistent"
            code = "value_mismatch"
        else:
            status = "consistent"
            code = None
    result = {
        "candidate_id": candidate_id,
        "status": status,
        "complete": status == "consistent",
        "observations": observations,
        "errors": errors,
    }
    if code is not None:
        result["issue"] = {"code": code}
    return result


def audit_rule(document, rule):
    """Evaluate one validated rule and preserve all comparison observations."""
    resolver = None
    comparisons = []
    rule_errors = []
    candidate_ids = [None]
    if rule["dynamic"]:
        try:
            resolver = CandidateResolver(document)
            candidate_ids = resolver.order
        except DataError as exc:
            rule_errors.append(exc.as_json())
            candidate_ids = []
    for candidate_id in candidate_ids:
        comparisons.append(_compare_group(document, rule, candidate_id, resolver))
    status = "not_run" if rule_errors else _rule_status(comparisons)
    return {
        "id": rule["id"],
        "status": status,
        "complete": status == "consistent",
        "comparisons": comparisons,
        "errors": rule_errors,
    }


def audit_document(document, rules_bundle):
    """Pure entry point for tests: validate and audit an in-memory JSON pair."""
    if type(document) is not dict:
        raise RuleFormatError("input document root must be an object")
    rules = validate_rules(rules_bundle)
    results = [audit_rule(document, rule) for rule in rules]
    counts = {status: 0 for status in STATUSES}
    for result in results:
        counts[result["status"]] += 1
    statuses = [result["status"] for result in results]
    if "inconsistent" in statuses:
        status = "inconsistent"
    elif "not_run" in statuses:
        status = "not_run"
    elif "different_scopes" in statuses:
        status = "different_scopes"
    else:
        status = "consistent"
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": document.get("case_id"),
        "status": status,
        "complete": status == "consistent",
        "summary": {
            "rules": len(results),
            "comparisons": sum(len(result["comparisons"]) for result in results),
            "consistent": counts["consistent"],
            "inconsistent": counts["inconsistent"],
            "different_scopes": counts["different_scopes"],
            "not_run": counts["not_run"],
        },
        "rules": results,
    }


def _parser():
    parser = argparse.ArgumentParser(
        description="Compare explicit same-semantic JSON pointers; never infer scientific validity."
    )
    parser.add_argument("--input", required=True, help="existing input JSON document")
    parser.add_argument("--rules", required=True, help="JSON object containing a rules array")
    parser.add_argument("--output", required=True, help="audit JSON to write atomically")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    output = os.path.realpath(args.output)
    if output in (os.path.realpath(args.input), os.path.realpath(args.rules)):
        sys.stderr.write("state_consistency: output must differ from input and rules\n")
        return 1
    try:
        rules_bundle = runtime.read_json(args.rules)
        document = runtime.read_json(args.input)
        report = audit_document(document, rules_bundle)
    except (OSError, runtime.JsonDataError, RuleFormatError) as exc:
        sys.stderr.write("state_consistency: %s\n" % exc)
        return 1
    try:
        runtime.write_json_atomic(args.output, report)
    except (OSError, runtime.JsonDataError) as exc:
        sys.stderr.write("state_consistency: could not write output: %s\n" % exc)
        return 1
    exit_code = 0 if report["complete"] else 2
    sys.stdout.write(
        "state_consistency: status=%s complete=%s comparisons=%d output=%s\n"
        % (report["status"], str(report["complete"]).lower(),
           report["summary"]["comparisons"], args.output)
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
