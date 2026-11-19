#!/usr/bin/env python3
"""Deterministic validator for the weekly-skill.plan-audit/v1 internal IR.

This report is not the organizer's case output contract. It checks exact
arithmetic, finite-domain membership, declared source locators/integrity, and
schedule results. It does not establish semantic source support, scientific
validity, safety, ethics, or approval.
"""

import argparse
import copy
import hashlib
import itertools
import json
import math
import os
import re
import sys
import tempfile
from fractions import Fraction


SCHEMA_VERSION = "weekly-skill.plan-audit/v1"
ENGINE_VERSION = "plan-audit/1"
VALIDATION_SCOPE = (
    "Machine checks cover structure, exact rational arithmetic, finite-domain "
    "membership/coverage, declared source locator and file-integrity facts, and "
    "the schedule auditor's returned result only. Source locators, raw-value "
    "matches, and hashes do not prove semantic source support; scientific "
    "meaning, source adequacy, feasibility outside the implemented constraints, "
    "safety, ethics, and execution approval still require the agent and qualified "
    "domain experts. Scientific readiness is a rollup of supplied review "
    "declarations, never scientific_or_safety_approval."
)
NUMERIC_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
MISSING = object()


def _reject_json_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def _stdlib_read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_json_constant)


def _read_json(path):
    try:
        from runtime import read_json
    except (ImportError, ModuleNotFoundError):
        return _stdlib_read_json(path)
    value = read_json(path)
    _check_finite_json(value)
    return value


def _check_finite_json(value, seen=None):
    if seen is None:
        seen = set()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in seen:
            raise ValueError("cyclic JSON value")
        seen.add(identity)
        if isinstance(value, dict):
            for child in value.values():
                _check_finite_json(child, seen)
        else:
            for child in value:
                _check_finite_json(child, seen)
        seen.remove(identity)


def _stdlib_sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path):
    try:
        from runtime import sha256_file
    except (ImportError, ModuleNotFoundError):
        return _stdlib_sha256_file(path)
    return str(sha256_file(path)).lower()


def _stdlib_write_json_atomic(path, value, compact=False):
    destination = os.path.abspath(path)
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    if compact:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=False, separators=(",", ":")
        ) + "\n"
    else:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".plan-audit-", suffix=".json", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _write_json_atomic(path, value, compact=False):
    if compact:
        _stdlib_write_json_atomic(path, value, compact=True)
        return
    try:
        from runtime import write_json_atomic
    except (ImportError, ModuleNotFoundError):
        _stdlib_write_json_atomic(path, value)
        return
    write_json_atomic(path, value)


def _json_pointer(document, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("invalid JSON Pointer")
    if pointer == "":
        return document
    current = document
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise KeyError("missing object key")
            current = current[token]
        elif isinstance(current, list):
            if not re.match(r"^(?:0|[1-9][0-9]*)$", token):
                raise KeyError("invalid array index")
            index = int(token)
            if index >= len(current):
                raise KeyError("array index out of range")
            current = current[index]
        else:
            raise KeyError("pointer traverses a scalar")
    return current


def _fraction_text(value):
    if value is None:
        return None
    if value.denominator == 1:
        return str(value.numerator)
    return str(value.numerator) + "/" + str(value.denominator)


def _is_numeric_string(value):
    return isinstance(value, str) and NUMERIC_RE.fullmatch(value) is not None


def _json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if isinstance(left, float) and not math.isfinite(left):
            return False
        if isinstance(right, float) and not math.isfinite(right):
            return False
        return Fraction(str(left)) == Fraction(str(right))
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return type(left) is type(right) and left == right


_DEFAULT_ARRAY_KEYS = {
    "parameters": "name",
    "cost_items": "id",
    "tasks": "id",
    "resource_calendars": "resource_id",
    "scientific_checks": "id",
}
_DEFAULT_DUPLICATE_CODES = {
    "parameters": "DUPLICATE_DEFAULT_PARAMETER_NAME",
    "cost_items": "DUPLICATE_DEFAULT_COST_ITEM_ID",
    "tasks": "DUPLICATE_DEFAULT_TASK_ID",
    "resource_calendars": "DUPLICATE_DEFAULT_RESOURCE_ID",
    "scientific_checks": "DUPLICATE_DEFAULT_SCIENTIFIC_CHECK_ID",
}
_DEFAULT_SOURCE_FIELDS = {
    "parameters": ("value", "domain", "unit"),
    "cost_items": (
        "quantity",
        "unit",
        "stock_role",
        "stock_available",
        "pack_size",
        "unit_price_minor",
        "currency",
        "fixed_cost_minor",
    ),
    "tasks": (
        "resources",
        "earliest_start",
        "deadline",
        "start",
        "duration_minutes",
    ),
    "resource_calendars": ("available_intervals", "capacity"),
    "scientific_checks": (),
}
_DEFAULT_CANDIDATE_FIELDS = frozenset(
    (
        "candidate_id",
        "parent_id",
        "parameters",
        "cost_items",
        "tasks",
        "resource_calendars",
        "scientific_checks",
        "budget_minor",
        "budget_currency",
        "horizon_minutes",
        "time_origin",
        "metrics",
        "declared_total_minor",
        "declared_totals_minor",
    )
)


def _default_entry_key(entry, field):
    if not isinstance(entry, dict):
        return None
    value = entry.get(_DEFAULT_ARRAY_KEYS[field])
    return value if isinstance(value, str) and value else None


def _merge_default_entries(
    defaults,
    overrides,
    field,
    positions,
    candidate_path,
    candidate_issues,
    trace,
):
    result = copy.deepcopy(defaults)
    seen_candidate_keys = set()
    merged_count = 0
    appended_count = 0
    for override_index, override in enumerate(overrides):
        key = _default_entry_key(override, field)
        if key is None or key not in positions or key in seen_candidate_keys:
            result.append(copy.deepcopy(override))
            appended_count += 1
            continue
        seen_candidate_keys.add(key)
        default = defaults[positions[key]]
        changed_source_fields = []
        for source_field in _DEFAULT_SOURCE_FIELDS[field]:
            if source_field not in override:
                continue
            if source_field not in default or not _json_equal(
                override[source_field], default[source_field]
            ):
                changed_source_fields.append(source_field)
        if changed_source_fields and not isinstance(override.get("source"), dict):
            _add_issue(
                candidate_issues,
                "validation",
                "DEFAULTS_SOURCE_REQUIRED",
                "%s/%s/%d/source" % (candidate_path, field, override_index),
                "This default-entry override changes %s. Supply a complete source object on the candidate entry; source fields are replaced, not inherited piecemeal. Changed resources includes nested units."
                % ", ".join(changed_source_fields),
            )
        merged = copy.deepcopy(default)
        merged.update(copy.deepcopy(override))
        result[positions[key]] = merged
        merged_count += 1
    if merged_count:
        trace["merged_entries"][field] = trace["merged_entries"].get(field, 0) + merged_count
    if appended_count:
        trace["appended_entries"][field] = trace["appended_entries"].get(field, 0) + appended_count
    return result


def _expand_defaults(document):
    if not isinstance(document, dict) or "defaults" not in document:
        return document, [], {}, None
    expanded = copy.deepcopy(document)
    defaults = expanded.pop("defaults")
    candidates = expanded.get("candidates")
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    input_issues = []
    trace = {
        "applied": isinstance(defaults, dict),
        "candidate_count": candidate_count,
        "merged_entries": {},
        "appended_entries": {},
        "semantics": "Mechanical shallow entry merges only; nested arrays are replaced, never concatenated.",
        "source_policy": "Changed inherited source-backed fields require an explicit complete candidate-entry source object; existing source audits still apply.",
    }
    if not isinstance(defaults, dict):
        _add_issue(
            input_issues,
            "structural",
            "DEFAULTS_OBJECT_REQUIRED",
            "/defaults",
            "defaults must be an object containing candidate-level fields and keyed default arrays; null is not an empty defaults object.",
            "input",
        )
        defaults = {}
    for field in defaults:
        if field not in _DEFAULT_CANDIDATE_FIELDS:
            _add_issue(
                input_issues,
                "structural",
                "DEFAULTS_FIELD_UNKNOWN",
                "/defaults/" + str(field),
                "Unknown defaults fields are rejected rather than copied into candidates.",
                "input",
            )
    default_positions = {}
    for field, key_name in _DEFAULT_ARRAY_KEYS.items():
        positions = {}
        default_positions[field] = positions
        if field not in defaults:
            continue
        entries = defaults[field]
        if not isinstance(entries, list):
            _add_issue(
                input_issues,
                "structural",
                "DEFAULTS_ARRAY_REQUIRED",
                "/defaults/" + field,
                field + " defaults must be an array keyed by " + key_name + ".",
                "input",
            )
            continue
        for index, entry in enumerate(entries):
            path = "/defaults/%s/%d" % (field, index)
            if not isinstance(entry, dict):
                _add_issue(
                    input_issues,
                    "structural",
                    "DEFAULTS_ENTRY_OBJECT_REQUIRED",
                    path,
                    "Each default " + field + " entry must be an object.",
                    "input",
                )
                continue
            key = _default_entry_key(entry, field)
            if key is None:
                _add_issue(
                    input_issues,
                    "structural",
                    "DEFAULTS_ENTRY_KEY_REQUIRED",
                    path + "/" + key_name,
                    "A default entry needs a nonempty string " + key_name + " for stable keyed merging.",
                    "input",
                )
                continue
            if key in positions:
                _add_issue(
                    input_issues,
                    "structural",
                    _DEFAULT_DUPLICATE_CODES[field],
                    path + "/" + key_name,
                    "Default " + key_name + " values must be unique; no last-value-wins merge is applied.",
                    "input",
                )
                continue
            positions[key] = index
    candidate_issues = {}
    if isinstance(candidates, list):
        for index in range(len(candidates)):
            candidate_issues[index] = [
                dict(issue, scope="machine") for issue in input_issues
            ]
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            merged_candidate = copy.deepcopy(defaults)
            merged_candidate.update(copy.deepcopy(candidate))
            candidate_path = "/candidates/%d" % index
            for field in _DEFAULT_ARRAY_KEYS:
                default_entries = defaults.get(field)
                override_entries = candidate.get(field)
                if not isinstance(default_entries, list) or not isinstance(
                    override_entries, list
                ):
                    continue
                merged_candidate[field] = _merge_default_entries(
                    default_entries,
                    override_entries,
                    field,
                    default_positions[field],
                    candidate_path,
                    candidate_issues[index],
                    trace,
                )
            candidates[index] = merged_candidate
    return expanded, input_issues, candidate_issues, trace


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Fraction):
        return _fraction_text(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return "<unserializable>"


def _add_issue(issues, kind, code, path, message, scope="machine"):
    if kind not in ("structural", "operational", "validation", "pending"):
        raise ValueError("invalid issue kind")
    issue = {
        "kind": kind,
        "scope": scope,
        "code": code,
        "path": path,
        "message": message,
    }
    issues.append(issue)
    return issue


def _parse_number(
    value,
    path,
    issues,
    scope="machine",
    nonnegative=False,
    positive=False,
):
    if isinstance(value, bool) or not isinstance(value, str) or not _is_numeric_string(value):
        _add_issue(
            issues,
            "structural",
            "NUMERIC_STRING_REQUIRED",
            path,
            "Expected a finite base-10 numeric string; booleans, JSON floats, NaN, Infinity, and rational literals are rejected.",
            scope,
        )
        return None
    try:
        number = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError):
        _add_issue(
            issues,
            "structural",
            "NUMERIC_STRING_REQUIRED",
            path,
            "The numeric string cannot be parsed exactly.",
            scope,
        )
        return None
    if positive and number <= 0:
        _add_issue(
            issues,
            "structural",
            "POSITIVE_NUMBER_REQUIRED",
            path,
            "The value must be strictly greater than zero.",
            scope,
        )
        return None
    if nonnegative and number < 0:
        _add_issue(
            issues,
            "structural",
            "NONNEGATIVE_NUMBER_REQUIRED",
            path,
            "The value cannot be negative.",
            scope,
        )
        return None
    return number


def _ceiling_fraction(value):
    return -((-value.numerator) // value.denominator)


class SourceAuditor:
    def __init__(self, registry, case_document, case_path, source_root):
        self.registry = registry if isinstance(registry, dict) else {}
        self.case_document = case_document
        self.case_path = os.path.realpath(case_path) if case_path else None
        self.source_root = os.path.realpath(source_root) if source_root else None

    def audit(self, source, path, issues, scope="machine", required=True):
        report = {
            "file": source.get("file") if isinstance(source, dict) else None,
            "registry_id": None,
            "locator_status": "pending",
            "raw_status": "not_supplied",
            "integrity_status": "not_checked",
            "status": "pending",
            "semantic_support": "not_assessed",
        }
        unavailable = (False, None)
        if source is None:
            if required:
                _add_issue(
                    issues,
                    "pending",
                    "SOURCE_MISSING",
                    path,
                    "No source was supplied; this check remains pending.",
                    scope,
                )
            else:
                report["status"] = "not_provided"
                report["locator_status"] = "not_provided"
            return report, unavailable
        if not isinstance(source, dict):
            _add_issue(
                issues,
                "structural",
                "SOURCE_OBJECT_REQUIRED",
                path,
                "A source must be an object with a local file and an appropriate locator.",
                scope,
            )
            report["status"] = "fail"
            return report, unavailable

        failed = False
        pending = False
        source_file = source.get("file")
        if not isinstance(source_file, str) or not source_file:
            _add_issue(
                issues,
                "pending",
                "SOURCE_FILE_MISSING",
                path + "/file",
                "The artifact file or registry key is missing; no source existence is assumed.",
                scope,
            )
            report["status"] = "pending"
            return report, unavailable

        artifact = {}
        if source_file in self.registry:
            candidate_artifact = self.registry[source_file]
            if not isinstance(candidate_artifact, dict):
                _add_issue(
                    issues,
                    "structural",
                    "SOURCE_REGISTRY_ENTRY_INVALID",
                    path,
                    "The referenced source_registry entry must be an object.",
                    scope,
                )
                report["status"] = "fail"
                return report, unavailable
            artifact = candidate_artifact
            report["registry_id"] = source_file
        actual_file = artifact.get("path", artifact.get("file", source_file))
        if not isinstance(actual_file, str) or not actual_file:
            _add_issue(
                issues,
                "structural",
                "SOURCE_REGISTRY_FILE_INVALID",
                path,
                "The registry entry does not identify a usable local file.",
                scope,
            )
            report["status"] = "fail"
            return report, unavailable

        media_type = artifact.get("media_type")
        if media_type is not None and not isinstance(media_type, str):
            _add_issue(
                issues,
                "structural",
                "SOURCE_MEDIA_TYPE_INVALID",
                path,
                "media_type must be a string when supplied.",
                scope,
            )
            failed = True
            media_type = None
        expected_hash = artifact.get("sha256")
        if expected_hash is not None and (
            not isinstance(expected_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) is None
        ):
            _add_issue(
                issues,
                "structural",
                "SOURCE_HASH_INVALID",
                path,
                "The declared SHA-256 must contain exactly 64 hexadecimal characters.",
                scope,
            )
            failed = True
            expected_hash = None

        resolved_path = None
        document = None
        is_case = False
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", actual_file):
            pending = True
            report["integrity_status"] = "pending" if expected_hash else "not_checked"
            _add_issue(
                issues,
                "pending",
                "NETWORK_SOURCE_NOT_FETCHED",
                path,
                "Network sources are never fetched by this deterministic auditor; provide a local artifact through --source-root.",
                scope,
            )
        else:
            if actual_file == "/input/case.json" and self.case_path:
                resolved_path = self.case_path
                document = self.case_document
                is_case = True
            elif os.path.isabs(actual_file):
                resolved_path = os.path.realpath(actual_file)
                if self.case_path and resolved_path == self.case_path:
                    document = self.case_document
                    is_case = True
            elif self.source_root:
                root = self.source_root
                resolved_path = os.path.realpath(os.path.join(root, actual_file))
                try:
                    contained = os.path.commonpath([root, resolved_path]) == root
                except ValueError:
                    contained = False
                if not contained:
                    failed = True
                    _add_issue(
                        issues,
                        "validation",
                        "SOURCE_PATH_OUTSIDE_ROOT",
                        path,
                        "A relative source path cannot escape --source-root.",
                        scope,
                    )
                    resolved_path = None
                elif self.case_path and resolved_path == self.case_path:
                    document = self.case_document
                    is_case = True
            else:
                pending = True
                _add_issue(
                    issues,
                    "pending",
                    "SOURCE_ROOT_REQUIRED",
                    path,
                    "A relative source path is unresolved until --source-root identifies its legitimate local root.",
                    scope,
                )

        if resolved_path:
            report["path_scope"] = (
                "case" if is_case else ("source_root" if not os.path.isabs(actual_file) else "absolute")
            )
            if expected_hash:
                try:
                    actual_hash = _sha256_file(resolved_path)
                    if actual_hash.lower() != expected_hash.lower():
                        failed = True
                        report["integrity_status"] = "mismatched"
                        _add_issue(
                            issues,
                            "validation",
                            "SOURCE_HASH_MISMATCH",
                            path,
                            "The local artifact hash differs from source_registry.sha256; this does not assess semantic support.",
                            scope,
                        )
                    else:
                        report["integrity_status"] = "matched"
                except (OSError, ValueError):
                    pending = True
                    report["integrity_status"] = "pending"
                    _add_issue(
                        issues,
                        "pending",
                        "SOURCE_ARTIFACT_UNAVAILABLE",
                        path,
                        "The artifact could not be read to verify its declared SHA-256.",
                        scope,
                    )
            elif not os.path.isfile(resolved_path):
                pending = True
                _add_issue(
                    issues,
                    "pending",
                    "SOURCE_ARTIFACT_UNAVAILABLE",
                    path,
                    "The declared local artifact is not currently readable; source support remains pending.",
                    scope,
                )

        suffix = os.path.splitext(actual_file)[1].lower()
        is_pdf = media_type == "application/pdf" or (media_type is None and suffix == ".pdf")
        is_json = (
            not is_pdf
            and (
                media_type in ("application/json", "text/json")
                or (media_type is None and (suffix == ".json" or is_case))
            )
        )
        pointer = source.get("pointer", MISSING)
        has_raw = "raw" in source
        quote = source.get("quote")

        if is_pdf:
            if pointer is not MISSING:
                failed = True
                _add_issue(
                    issues,
                    "structural",
                    "PDF_POINTER_NOT_SUPPORTED",
                    path + "/pointer",
                    "PDF sources use page plus a human-review locator instead of JSON Pointer.",
                    scope,
                )
            valid_page = (
                isinstance(source.get("page"), int)
                and not isinstance(source.get("page"), bool)
                and source.get("page") >= 1
            )
            valid_locator = isinstance(source.get("locator"), str) and bool(source.get("locator"))
            if valid_page and valid_locator:
                report["locator_status"] = "declared"
            else:
                pending = True
                report["locator_status"] = "pending"
                _add_issue(
                    issues,
                    "pending",
                    "PDF_LOCATOR_REQUIRED",
                    path,
                    "A PDF source needs a positive one-based page and a section/table/figure locator before it can support even a declared scientific pass.",
                    scope,
                )
            if has_raw:
                pending = True
                report["raw_status"] = "pending"
                _add_issue(
                    issues,
                    "pending",
                    "PDF_RAW_UNCHECKED",
                    path + "/raw",
                    "PDF content is not decoded by this stdlib engine; the supplied raw value remains unchecked.",
                    scope,
                )
        elif is_json:
            if pointer is MISSING:
                pending = True
                report["locator_status"] = "pending"
                _add_issue(
                    issues,
                    "pending",
                    "SOURCE_POINTER_REQUIRED",
                    path,
                    "A JSON source needs an RFC 6901 pointer, including for /input/case.json.",
                    scope,
                )
            elif not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
                failed = True
                _add_issue(
                    issues,
                    "structural",
                    "SOURCE_POINTER_INVALID",
                    path + "/pointer",
                    "JSON Pointer must be empty or begin with '/'.",
                    scope,
                )
            elif resolved_path and not failed:
                if document is None:
                    try:
                        document = _read_json(resolved_path)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        pending = True
                        _add_issue(
                            issues,
                            "pending",
                            "SOURCE_JSON_UNAVAILABLE",
                            path,
                            "The JSON artifact could not be parsed, so its pointer and raw value remain unchecked.",
                            scope,
                        )
                if document is not None:
                    try:
                        actual_raw = _json_pointer(document, pointer)
                        unavailable = (True, actual_raw)
                        report["locator_status"] = "resolved"
                        if has_raw:
                            if _json_equal(actual_raw, source.get("raw")):
                                report["raw_status"] = "matched"
                            else:
                                failed = True
                                report["raw_status"] = "mismatched"
                                _add_issue(
                                    issues,
                                    "validation",
                                    "SOURCE_RAW_MISMATCH",
                                    path + "/raw",
                                    "The exact, type-sensitive JSON value at the pointer differs from source.raw; numeric strings are not coerced to numbers.",
                                    scope,
                                )
                        if quote is not None and isinstance(actual_raw, str):
                            if not isinstance(quote, str) or quote not in actual_raw:
                                failed = True
                                _add_issue(
                                    issues,
                                    "validation",
                                    "SOURCE_QUOTE_MISMATCH",
                                    path + "/quote",
                                    "The literal quote is not present in the string at the resolved pointer.",
                                    scope,
                                )
                    except (KeyError, IndexError, ValueError, TypeError):
                        failed = True
                        report["locator_status"] = "failed"
                        if has_raw:
                            report["raw_status"] = "pending"
                        _add_issue(
                            issues,
                            "validation",
                            "SOURCE_POINTER_UNRESOLVED",
                            path + "/pointer",
                            "The RFC 6901 pointer does not resolve in the readable JSON artifact.",
                            scope,
                        )
            else:
                pending = True
                if has_raw:
                    report["raw_status"] = "pending"
        else:
            if pointer is not MISSING or has_raw:
                pending = True
                _add_issue(
                    issues,
                    "pending",
                    "SOURCE_CONTENT_UNCHECKED",
                    path,
                    "This media type has no stdlib content decoder; pointer/raw assertions remain unchecked.",
                    scope,
                )
            if isinstance(source.get("locator"), str) and source.get("locator"):
                report["locator_status"] = "declared"
            else:
                pending = True
                _add_issue(
                    issues,
                    "pending",
                    "SOURCE_LOCATOR_REQUIRED",
                    path,
                    "A non-JSON source needs a human-review locator; a file label alone is insufficient.",
                    scope,
                )

        if failed:
            report["status"] = "fail"
        elif pending:
            report["status"] = "pending"
        else:
            report["status"] = "pass"
        return report, unavailable


class PlanAuditor:
    def __init__(
        self,
        document,
        case_document=None,
        case_path=None,
        source_root=None,
        expected_candidates=None,
        exhaustive=False,
        search_limit=100000,
        initial_issues=None,
        input_path=None,
    ):
        document, default_input_issues, self.defaults_candidate_issues, defaults_trace = _expand_defaults(
            document
        )
        self.document = document
        self.case_document = case_document
        self.case_path = case_path
        self.expected_candidates = expected_candidates
        self.exhaustive = exhaustive
        self.search_limit = search_limit
        self.input_issues = list(initial_issues or []) + default_input_issues
        self.search_issues = []
        self.ranking_issues = []
        self.source_summaries = []
        self.internal_candidates = {}
        registry = document.get("source_registry", {}) if isinstance(document, dict) else {}
        self.sources = SourceAuditor(registry, case_document, case_path, source_root)
        self.report = {
            "schema_version": SCHEMA_VERSION + ".report",
            "engine_version": ENGINE_VERSION,
            "case_id": document.get("case_id") if isinstance(document, dict) else None,
            "input_path": input_path,
            "status": "pending",
            "scientific_or_safety_approval": False,
            "validation_scope": VALIDATION_SCOPE,
            "case_output_contract": False,
            "internal_ir_contract": SCHEMA_VERSION,
            "example_notice": (
                document.get("example_notice")
                if isinstance(document, dict) and isinstance(document.get("example_notice"), str)
                else None
            ),
            "input_issues": self.input_issues,
            "candidates": [],
            "candidate_status_counts": {"pass": 0, "fail": 0, "pending": 0, "error": 0},
            "issue_counts": {},
            "search": {},
            "ranking": {},
            "pending_expert_roles": [],
            "pending_inputs": [],
            "exit_code": 2,
        }
        if defaults_trace is not None:
            self.report["defaults_trace"] = defaults_trace

    def run(self):
        if not isinstance(self.document, dict):
            _add_issue(
                self.input_issues,
                "structural",
                "INPUT_OBJECT_REQUIRED",
                "/",
                "Audit input must be a JSON object.",
                "input",
            )
            self._finish()
            return self.report
        if self.document.get("schema_version") != SCHEMA_VERSION:
            _add_issue(
                self.input_issues,
                "structural",
                "SCHEMA_VERSION_MISMATCH",
                "/schema_version",
                "Expected weekly-skill.plan-audit/v1.",
                "input",
            )
        case_id = self.document.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            _add_issue(
                self.input_issues,
                "structural",
                "CASE_ID_REQUIRED",
                "/case_id",
                "A nonempty case_id is required.",
                "input",
            )
        if isinstance(self.case_document, dict) and "case_id" in self.case_document:
            actual_case_id = self.case_document.get("case_id")
            if case_id != actual_case_id:
                _add_issue(
                    self.input_issues,
                    "validation",
                    "CASE_ID_MISMATCH",
                    "/case_id",
                    "The audit case_id does not match the case_id in the supplied --case artifact.",
                    "input",
                )
        if "source_registry" in self.document and not isinstance(self.document.get("source_registry"), dict):
            _add_issue(
                self.input_issues,
                "structural",
                "SOURCE_REGISTRY_OBJECT_REQUIRED",
                "/source_registry",
                "source_registry must be an object keyed by artifact identifiers.",
                "input",
            )
        if "priority" in self.document and not isinstance(self.document.get("priority"), list):
            _add_issue(
                self.input_issues,
                "structural",
                "PRIORITY_ARRAY_REQUIRED",
                "/priority",
                "priority must be an array of metric/direction objects.",
                "ranking",
            )
        candidates = self.document.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            _add_issue(
                self.input_issues,
                "structural",
                "CANDIDATES_REQUIRED",
                "/candidates",
                "candidates must be a nonempty array; the engine does not invent replacement candidates.",
                "input",
            )
            candidates = []
        if self.expected_candidates is not None and len(candidates) != self.expected_candidates:
            _add_issue(
                self.input_issues,
                "validation",
                "CANDIDATE_COUNT_MISMATCH",
                "/candidates",
                "Expected %d supplied candidates but found %d; no candidate was cloned or fabricated."
                % (self.expected_candidates, len(candidates)),
                "input",
            )

        identifiers = set()
        for index, candidate in enumerate(candidates):
            candidate_report = self._audit_candidate(candidate, index, identifiers)
            self.report["candidates"].append(candidate_report)
        self._validate_parent_links(candidates)
        self.report["search"] = self._audit_search(candidates)
        self.report["ranking"] = self._audit_ranking()
        self.report["pending_expert_roles"] = sorted(
            {
                item["expert_role"]
                for candidate in self.report["candidates"]
                for item in candidate.get("pending_experts", [])
                if item.get("expert_role")
            }
        )
        pending_inputs = []
        for issue in self._all_issues():
            if issue["kind"] == "pending":
                pending_inputs.append(
                    {
                        "code": issue["code"],
                        "path": issue["path"],
                        "scope": issue["scope"],
                    }
                )
        self.report["pending_inputs"] = pending_inputs
        self._finish()
        return self.report

    def _audit_candidate(self, candidate, index, identifiers):
        path = "/candidates/%d" % index
        issues = list(self.defaults_candidate_issues.get(index, []))
        fallback_id = "candidate[%d]" % index
        if not isinstance(candidate, dict):
            _add_issue(
                issues,
                "structural",
                "CANDIDATE_OBJECT_REQUIRED",
                path,
                "Each candidate must be an object.",
            )
            return {
                "candidate_id": fallback_id,
                "parent_id": None,
                "status": "error",
                "machine_status": "error",
                "machine_pass": False,
                "scientific_readiness": "pending",
                "parameters": [],
                "cost": {},
                "tasks": [],
                "schedule": {"status": "pending", "reason": "candidate_structure_invalid"},
                "scientific_checks": [],
                "metrics": {},
                "source_summary": {"pass": 0, "fail": 0, "pending": 0, "not_provided": 0},
                "pending_experts": [],
                "issues": issues,
            }
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            _add_issue(
                issues,
                "structural",
                "CANDIDATE_ID_REQUIRED",
                path + "/candidate_id",
                "candidate_id must be a nonempty string.",
            )
            candidate_id = fallback_id
        elif candidate_id in identifiers:
            _add_issue(
                issues,
                "structural",
                "DUPLICATE_CANDIDATE_ID",
                path + "/candidate_id",
                "candidate_id values must be unique.",
            )
        identifiers.add(candidate_id)
        parent_id = candidate.get("parent_id")
        if "parent_id" in candidate and parent_id is not None and (not isinstance(parent_id, str) or not parent_id):
            _add_issue(
                issues,
                "structural",
                "PARENT_ID_INVALID",
                path + "/parent_id",
                "parent_id must be null for a root or a nonempty string identifying its supplied source version.",
            )

        for field in ("parameters", "cost_items", "tasks", "resource_calendars", "scientific_checks"):
            if field not in candidate or not isinstance(candidate.get(field), list):
                _add_issue(
                    issues,
                    "structural",
                    "CANDIDATE_ARRAY_REQUIRED",
                    path + "/" + field,
                    field + " is required and must be an array; missing data is not replaced.",
                )

        parameter_reports, parameter_internal = self._audit_parameters(candidate, path, issues)
        cost_report = self._audit_costs(candidate, path, issues)
        task_reports = self._audit_task_sources(candidate, path, issues)
        calendar_source_reports = self._audit_calendar_sources(candidate, path, issues)
        schedule_report = self._audit_schedule(candidate, path, issues)
        if calendar_source_reports:
            schedule_report["calendar_sources"] = calendar_source_reports
        schedule_report["horizon_audit"] = self._audit_horizon(
            candidate, schedule_report, path, issues
        )
        scientific_reports, scientific_status, pending_experts = self._audit_scientific(
            candidate, path, issues
        )
        metrics_report = self._audit_candidate_metrics(candidate, path, issues)
        if "budget_currency" in candidate and (
            not isinstance(candidate.get("budget_currency"), str) or not candidate.get("budget_currency")
        ):
            _add_issue(
                issues,
                "structural",
                "BUDGET_CURRENCY_INVALID",
                path + "/budget_currency",
                "budget_currency must be a nonempty currency identifier when supplied.",
            )

        source_statuses = []
        for item in parameter_reports:
            source_statuses.append(item["source"]["status"])
            if item.get("normalization", {}).get("source") is not None:
                source_statuses.append(item["normalization"]["source"]["status"])
        for item in cost_report.get("items", []):
            source_statuses.append(item["source"]["status"])
        for item in task_reports:
            source_statuses.append(item["source"]["status"])
        for item in calendar_source_reports:
            source_statuses.append(item["source"]["status"])
        for item in scientific_reports:
            if item.get("source") is not None:
                source_statuses.append(item["source"]["status"])
        source_summary = {"pass": 0, "fail": 0, "pending": 0, "not_provided": 0}
        for status in source_statuses:
            source_summary[status if status in source_summary else "pending"] += 1

        machine_kinds = {
            issue["kind"] for issue in issues if issue["scope"] == "machine"
        }
        if "operational" in machine_kinds or "structural" in machine_kinds:
            machine_status = "error"
        elif "validation" in machine_kinds:
            machine_status = "fail"
        elif "pending" in machine_kinds:
            machine_status = "pending"
        else:
            machine_status = "pass"

        all_kinds = {issue["kind"] for issue in issues}
        if "operational" in all_kinds or "structural" in all_kinds:
            status = "error"
        elif machine_status == "fail" or scientific_status == "fail" or "validation" in all_kinds:
            status = "fail"
        elif machine_status == "pending" or scientific_status == "pending":
            status = "pending"
        else:
            status = "pass"
        result = {
            "candidate_id": candidate_id,
            "parent_id": parent_id if isinstance(parent_id, str) else None,
            "status": status,
            "machine_status": machine_status,
            "machine_pass": machine_status == "pass",
            "scientific_readiness": scientific_status,
            "scientific_semantics_independently_verified": False,
            "parameters": parameter_reports,
            "cost": cost_report,
            "tasks": task_reports,
            "schedule": schedule_report,
            "scientific_checks": scientific_reports,
            "metrics": metrics_report,
            "source_summary": source_summary,
            "pending_experts": pending_experts,
            "issues": issues,
        }
        self.internal_candidates[index] = {
            "id": candidate_id,
            "parameters": parameter_internal,
            "candidate": candidate,
            "issues": issues,
        }
        return result

    def _audit_parameters(self, candidate, candidate_path, issues):
        reports = []
        internal = []
        parameters = candidate.get("parameters")
        if not isinstance(parameters, list):
            return reports, internal
        names = set()
        for index, parameter in enumerate(parameters):
            path = candidate_path + "/parameters/%d" % index
            if not isinstance(parameter, dict):
                _add_issue(
                    issues,
                    "structural",
                    "PARAMETER_OBJECT_REQUIRED",
                    path,
                    "Each parameter must be an object.",
                )
                continue
            name = parameter.get("name")
            if not isinstance(name, str) or not name:
                _add_issue(
                    issues,
                    "structural",
                    "PARAMETER_NAME_REQUIRED",
                    path + "/name",
                    "A parameter needs a nonempty name.",
                )
                name = "parameter[%d]" % index
            elif name in names:
                _add_issue(
                    issues,
                    "structural",
                    "DUPLICATE_PARAMETER_NAME",
                    path + "/name",
                    "Parameter names must be unique within a candidate.",
                )
            names.add(name)
            unit = parameter.get("unit")
            if not isinstance(unit, str) or not unit:
                _add_issue(
                    issues,
                    "structural",
                    "PARAMETER_UNIT_REQUIRED",
                    path + "/unit",
                    "A literal unit is required; no unit conversion is inferred.",
                )
                unit = None
            source = parameter.get("source")
            source_report, raw_access = self.sources.audit(source, path + "/source", issues)
            domain, domain_report, domain_error = self._parse_domain(
                parameter.get("domain", MISSING), path + "/domain", issues, unit
            )
            value = parameter.get("value")
            if not isinstance(value, str) or not value:
                _add_issue(
                    issues,
                    "structural",
                    "PARAMETER_VALUE_REQUIRED",
                    path + "/value",
                    "Parameter value must be a numeric or categorical string; booleans are not numeric.",
                )
                value = None
            parsed_value = None
            membership = "pending"
            if domain is not None and value is not None:
                if domain["kind"] == "numeric":
                    if _is_numeric_string(value):
                        parsed_value = Fraction(value)
                        membership = "pass" if parsed_value in domain["allowed_set"] else "fail"
                    else:
                        membership = "fail"
                        _add_issue(
                            issues,
                            "structural",
                            "NUMERIC_PARAMETER_VALUE_REQUIRED",
                            path + "/value",
                            "A numeric domain requires an exact numeric string value.",
                        )
                elif domain["kind"] == "interval":
                    if _is_numeric_string(value):
                        parsed_value = Fraction(value)
                        in_closed_interval = domain["min"] <= parsed_value <= domain["max"]
                        quotient = (parsed_value - domain["origin"]) / domain["step"]
                        on_grid = quotient.denominator == 1
                        membership = "pass" if in_closed_interval and on_grid else "fail"
                    else:
                        membership = "fail"
                        _add_issue(
                            issues,
                            "structural",
                            "NUMERIC_PARAMETER_VALUE_REQUIRED",
                            path + "/value",
                            "An interval domain requires an exact numeric string value.",
                        )
                elif domain["kind"] == "mixed":
                    parsed_value = Fraction(value) if _is_numeric_string(value) else value
                    membership = "pass" if parsed_value in domain["allowed_set"] else "fail"
                else:
                    parsed_value = value
                    membership = "pass" if value in domain["allowed_set"] else "fail"
                if membership == "fail" and not (
                    domain["kind"] in ("numeric", "interval") and not _is_numeric_string(value)
                ):
                    _add_issue(
                        issues,
                        "validation",
                        "PARAMETER_OUT_OF_DOMAIN",
                        path + "/value",
                        "The value is outside the explicit set, outside the closed interval, or off the exact origin+k*step grid; it was not clamped.",
                    )
            normalization_report = self._audit_normalization(
                parameter,
                path,
                issues,
                source,
                unit,
                parsed_value,
                raw_access,
                domain is not None
                and (
                    domain["kind"] in ("numeric", "interval")
                    or (domain["kind"] == "mixed" and isinstance(parsed_value, Fraction))
                ),
            )
            domain_id = "%s/parameter/%s" % (self._current_candidate_id(candidate_path), name)
            report = {
                "domain_id": domain_id,
                "name": name,
                "value": value,
                "canonical_value": _fraction_text(parsed_value)
                if isinstance(parsed_value, Fraction)
                else parsed_value,
                "unit": unit,
                "membership": membership,
                "domain": domain_report,
                "source_dimension": {
                    "declared_unit": unit,
                    "source_unit": source.get("unit") if isinstance(source, dict) else None,
                    "status": "pending",
                },
                "normalization": normalization_report,
                "source": source_report,
            }
            source_unit = source.get("unit") if isinstance(source, dict) else None
            if source_unit is not None and not isinstance(source_unit, str):
                _add_issue(
                    issues,
                    "structural",
                    "SOURCE_UNIT_INVALID",
                    path + "/source/unit",
                    "source.unit must be a literal string when supplied.",
                )
                report["source_dimension"]["status"] = "fail"
            elif source_unit and unit and source_unit == unit:
                report["source_dimension"]["status"] = "matched"
            elif source_unit and unit and normalization_report.get("status") == "pass":
                report["source_dimension"]["status"] = "normalized"
            elif source_unit and unit:
                _add_issue(
                    issues,
                    "validation",
                    "UNIT_MISMATCH",
                    path + "/unit",
                    "Source and normalized units differ without a verified explicit normalization; no silent conversion was applied.",
                )
                report["source_dimension"]["status"] = "fail"
            else:
                report["source_dimension"]["status"] = "declared_only"
            reports.append(report)
            internal.append(
                {
                    "name": name,
                    "domain": domain,
                    "domain_error": domain_error,
                    "value": value,
                    "parsed_value": parsed_value,
                    "unit": unit,
                    "membership": membership,
                    "domain_id": domain_id,
                }
            )
        return reports, internal

    def _current_candidate_id(self, candidate_path):
        try:
            index = int(candidate_path.rsplit("/", 1)[1])
            candidate = self.document.get("candidates", [])[index]
            value = candidate.get("candidate_id")
            if isinstance(value, str) and value:
                return value
        except (ValueError, IndexError, AttributeError, TypeError):
            pass
        return "candidate" + candidate_path.replace("/", "_")

    def _parse_domain(self, domain_value, path, issues, parameter_unit):
        if domain_value is MISSING:
            _add_issue(
                issues,
                "structural",
                "DOMAIN_REQUIRED",
                path,
                "Every parameter needs an explicit finite set or a finite stepped interval.",
            )
            return None, {"kind": "invalid", "finite": False}, True
        if isinstance(domain_value, list):
            if not domain_value:
                _add_issue(
                    issues,
                    "structural",
                    "DOMAIN_EMPTY",
                    path,
                    "An explicit domain cannot be empty.",
                )
                return None, {"kind": "invalid", "finite": False}, True
            if any(not isinstance(value, str) or not value for value in domain_value):
                _add_issue(
                    issues,
                    "structural",
                    "DOMAIN_STRING_VALUES_REQUIRED",
                    path,
                    "Explicit domain entries must be nonempty numeric or categorical strings.",
                )
                return None, {"kind": "invalid", "finite": False}, True
            flags = [_is_numeric_string(value) for value in domain_value]
            kind = "numeric" if all(flags) else ("categorical" if not any(flags) else "mixed")
            canonical = [
                _fraction_text(Fraction(value)) if numeric else value
                for value, numeric in zip(domain_value, flags)
            ]
            allowed = [
                Fraction(value) if numeric else value
                for value, numeric in zip(domain_value, flags)
            ]
            if len(set(allowed)) != len(allowed):
                _add_issue(
                    issues,
                    "structural",
                    "DUPLICATE_DOMAIN_VALUE",
                    path,
                    "Domain values must be unique after exact per-entry numeric normalization.",
                )
                return None, {"kind": "invalid", "finite": False}, True
            return (
                {
                    "kind": kind,
                    "allowed": allowed,
                    "allowed_set": set(allowed),
                    "unit": parameter_unit,
                },
                {
                    "kind": "explicit_" + kind,
                    "finite": True,
                    "count": len(allowed),
                    "allowed_values": canonical,
                    "closed_endpoints": None,
                    "step_rule": None,
                },
                False,
            )
        if not isinstance(domain_value, dict):
            _add_issue(
                issues,
                "structural",
                "DOMAIN_INVALID",
                path,
                "Domain must be an explicit string array or a stepped interval object.",
            )
            return None, {"kind": "invalid", "finite": False}, True
        for required in ("min", "max", "step"):
            if required not in domain_value:
                _add_issue(
                    issues,
                    "structural",
                    "INTERVAL_FIELD_REQUIRED",
                    path + "/" + required,
                    "A finite interval requires min, max, and positive step.",
                )
        if any(key not in ("min", "max", "step", "origin", "unit") for key in domain_value):
            _add_issue(
                issues,
                "structural",
                "INTERVAL_FIELD_UNKNOWN",
                path,
                "Unknown interval fields are rejected rather than interpreted.",
            )
        min_value = _parse_number(domain_value.get("min"), path + "/min", issues)
        max_value = _parse_number(domain_value.get("max"), path + "/max", issues)
        step = _parse_number(domain_value.get("step"), path + "/step", issues)
        origin = (
            _parse_number(domain_value.get("origin"), path + "/origin", issues)
            if "origin" in domain_value
            else min_value
        )
        domain_unit = domain_value.get("unit")
        if "unit" in domain_value and (not isinstance(domain_unit, str) or not domain_unit):
            _add_issue(
                issues,
                "structural",
                "DOMAIN_UNIT_INVALID",
                path + "/unit",
                "Interval domain unit must be a nonempty literal string.",
            )
        if parameter_unit and isinstance(domain_unit, str) and parameter_unit != domain_unit:
            _add_issue(
                issues,
                "validation",
                "DOMAIN_UNIT_MISMATCH",
                path + "/unit",
                "Domain and parameter units differ; provide an explicitly normalized IR instead of relying on conversion.",
            )
        if any(value is None for value in (min_value, max_value, step, origin)):
            return None, {"kind": "interval", "finite": False}, True
        if step == 0:
            _add_issue(
                issues,
                "structural",
                "ZERO_DOMAIN_STEP",
                path + "/step",
                "A zero step is invalid and cannot define a finite grid.",
            )
            return None, {"kind": "interval", "finite": False}, True
        if step < 0:
            _add_issue(
                issues,
                "structural",
                "NEGATIVE_DOMAIN_STEP",
                path + "/step",
                "Step must be strictly positive; reverse-order grids are not inferred.",
            )
            return None, {"kind": "interval", "finite": False}, True
        if min_value > max_value:
            _add_issue(
                issues,
                "structural",
                "EMPTY_INTERVAL",
                path,
                "Closed interval min cannot exceed max.",
            )
            return None, {"kind": "interval", "finite": False}, True
        return (
            {
                "kind": "interval",
                "min": min_value,
                "max": max_value,
                "step": step,
                "origin": origin,
                "unit": domain_unit or parameter_unit,
            },
            {
                "kind": "stepped_interval",
                "finite": True,
                "count": self._interval_count(min_value, max_value, origin, step),
                "min": _fraction_text(min_value),
                "max": _fraction_text(max_value),
                "origin": _fraction_text(origin),
                "step": _fraction_text(step),
                "unit": domain_unit or parameter_unit,
                "closed_endpoints": True,
                "step_rule": "value is in [min,max] and (value-origin)/step is an exact integer",
            },
            False,
        )

    @staticmethod
    def _interval_bounds(min_value, max_value, origin, step):
        lower = _ceiling_fraction((min_value - origin) / step)
        upper_value = (max_value - origin) / step
        upper = upper_value.numerator // upper_value.denominator
        return lower, upper

    @classmethod
    def _interval_count(cls, min_value, max_value, origin, step):
        lower, upper = cls._interval_bounds(min_value, max_value, origin, step)
        return max(0, upper - lower + 1)

    def _audit_normalization(
        self,
        parameter,
        path,
        issues,
        source,
        unit,
        parsed_value,
        raw_access,
        numeric_domain,
    ):
        normalization = parameter.get("normalization", MISSING)
        if normalization is MISSING:
            return {"status": "not_provided", "source": None}
        if not isinstance(normalization, dict):
            _add_issue(
                issues,
                "structural",
                "NORMALIZATION_OBJECT_REQUIRED",
                path + "/normalization",
                "normalization must declare factor, result unit, and provenance.",
            )
            return {"status": "fail", "source": None}
        factor = _parse_number(
            normalization.get("factor"),
            path + "/normalization/factor",
            issues,
        )
        if factor == 0:
            _add_issue(
                issues,
                "structural",
                "ZERO_NORMALIZATION_FACTOR",
                path + "/normalization/factor",
                "A normalization factor must be nonzero.",
            )
            factor = None
        result_unit = normalization.get("unit")
        if not isinstance(result_unit, str) or not result_unit:
            _add_issue(
                issues,
                "structural",
                "NORMALIZATION_UNIT_REQUIRED",
                path + "/normalization/unit",
                "The normalization result unit is required.",
            )
        elif unit and result_unit != unit:
            _add_issue(
                issues,
                "validation",
                "NORMALIZATION_UNIT_MISMATCH",
                path + "/normalization/unit",
                "normalization.unit must literally equal parameter.unit.",
            )
        factor_source_report, _ = self.sources.audit(
            normalization.get("source"), path + "/normalization/source", issues
        )
        report = {
            "factor": _fraction_text(factor),
            "unit": result_unit if isinstance(result_unit, str) else None,
            "source": factor_source_report,
            "formula": "normalized_value = source.raw * factor",
            "status": "pending",
        }
        if not numeric_domain:
            _add_issue(
                issues,
                "structural",
                "NORMALIZATION_NUMERIC_DOMAIN_REQUIRED",
                path + "/normalization",
                "Explicit normalization is meaningful only for a numeric domain.",
            )
            report["status"] = "fail"
            return report
        source_unit = source.get("unit") if isinstance(source, dict) else None
        if not source_unit:
            _add_issue(
                issues,
                "pending",
                "NORMALIZATION_SOURCE_UNIT_MISSING",
                path + "/source/unit",
                "The pre-normalization source unit is not declared, so unit consistency remains pending.",
            )
        available, raw = raw_access
        if factor is not None and isinstance(parsed_value, Fraction) and available:
            if _is_numeric_string(raw):
                raw_number = Fraction(raw)
            elif isinstance(raw, int) and not isinstance(raw, bool):
                raw_number = Fraction(raw)
            else:
                raw_number = None
            if raw_number is None:
                _add_issue(
                    issues,
                    "validation",
                    "NORMALIZATION_RAW_NOT_EXACT",
                    path + "/source/raw",
                    "The resolved source.raw is not an exact numeric string or JSON integer; JSON floats are not used for conversion arithmetic.",
                )
                report["status"] = "fail"
            elif raw_number * factor == parsed_value:
                report["status"] = "pass" if source_unit else "pending"
                report["arithmetic_status"] = "matched"
            else:
                _add_issue(
                    issues,
                    "validation",
                    "NORMALIZATION_ARITHMETIC_MISMATCH",
                    path + "/value",
                    "The normalized value does not exactly equal source.raw multiplied by normalization.factor.",
                )
                report["status"] = "fail"
                report["arithmetic_status"] = "mismatched"
        else:
            report["arithmetic_status"] = "pending"
            _add_issue(
                issues,
                "pending",
                "NORMALIZATION_UNVERIFIED",
                path + "/normalization",
                "The normalized value cannot be recomputed until the numeric value, factor, and exact source.raw are available.",
            )
        if report["status"] != "fail" and factor_source_report["status"] == "fail":
            report["status"] = "fail"
        elif report["status"] == "pass" and factor_source_report["status"] != "pass":
            report["status"] = "pending"
        return report

    def _audit_costs(self, candidate, candidate_path, issues):
        items_value = candidate.get("cost_items")
        report = {
            "items": [],
            "currencies": {},
            "declared_comparisons": [],
            "budget": {"status": "not_provided"},
            "rules": {
                "legacy_unspecified": "Preserve pre-stock_role behavior: purchase-style shortfall and billed*unit_price_minor; missing stock keeps cost/deficit completeness pending.",
                "capacity": "Capacity is a usage limit, never a procurement deduction. packs=ceil(quantity/pack_size), item_cost=billed*unit_price_minor, capacity_margin=stock_available-quantity; quantity>capacity fails while known gross cost remains reportable.",
                "capacity_unknown": "Known all-consumption gross price remains complete while capacity availability is independently pending.",
                "purchase": "Pre-owned stock is explicit: shortfall=max(0,quantity-stock) is procurement need only, packs=ceil(shortfall/pack_size), billed=packs*pack_size, and item_cost=billed*unit_price_minor. shortfall is never the pack-priced charge quantity; pack_rounded_gross_cost_minor repeats this same conservative cost for report compatibility.",
                "candidate_total": "sum known billed_quantity*unit_price_minor item costs per currency + all known fixed charges",
                "budget": "pass only when complete comparable known total plus fixed charges is <= budget; known total above budget fails even with unknown lines",
            },
        }
        if not isinstance(items_value, list):
            return report
        groups = {}
        item_identifiers = set()
        for index, item in enumerate(items_value):
            path = candidate_path + "/cost_items/%d" % index
            if not isinstance(item, dict):
                _add_issue(
                    issues,
                    "structural",
                    "COST_ITEM_OBJECT_REQUIRED",
                    path,
                    "Each cost item must be an object.",
                )
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                _add_issue(
                    issues,
                    "structural",
                    "COST_ITEM_ID_REQUIRED",
                    path + "/id",
                    "A nonempty cost item id is required.",
                )
                item_id = "cost[%d]" % index
            elif item_id in item_identifiers:
                _add_issue(
                    issues,
                    "structural",
                    "DUPLICATE_COST_ITEM_ID",
                    path + "/id",
                    "Cost item ids must be unique within a candidate.",
                )
            item_identifiers.add(item_id)
            stock_role = item.get("stock_role")
            stock_role_status = "legacy_unspecified" if "stock_role" not in item else "valid"
            if "stock_role" in item and stock_role not in ("capacity", "purchase", "none"):
                stock_role_status = "invalid"
                _add_issue(
                    issues,
                    "structural",
                    "STOCK_ROLE_INVALID",
                    path + "/stock_role",
                    "stock_role must be 'capacity', 'purchase', or source-justified 'none'; no role implies free stock or available capacity.",
                )
                stock_role = None
            if stock_role == "none" and "stock_available" in item:
                _add_issue(
                    issues,
                    "structural",
                    "STOCK_ROLE_STOCK_CONFLICT",
                    path + "/stock_available",
                    "Gross pricing without a stock rule cannot discard a supplied stock/capacity fact; assign its actual role instead.",
                )
            source_report, _ = self.sources.audit(item.get("source"), path + "/source", issues)
            unit = item.get("unit")
            if not isinstance(unit, str) or not unit:
                _add_issue(
                    issues,
                    "structural",
                    "COST_UNIT_REQUIRED",
                    path + "/unit",
                    "A literal quantity/billing unit is required.",
                )
            source_unit = item.get("source", {}).get("unit") if isinstance(item.get("source"), dict) else None
            if source_unit is not None and source_unit != unit:
                _add_issue(
                    issues,
                    "validation",
                    "COST_UNIT_MISMATCH",
                    path + "/unit",
                    "The source and cost item units differ; no silent conversion or pack inference was applied.",
                )
            currency = item.get("currency")
            if not isinstance(currency, str) or not currency:
                _add_issue(
                    issues,
                    "structural",
                    "CURRENCY_REQUIRED",
                    path + "/currency",
                    "Every cost item requires a nonempty currency; missing currency totals are never folded together.",
                )
                currency = None
            quantity = _parse_number(item.get("quantity"), path + "/quantity", issues, nonnegative=True)
            stock = (
                _parse_number(
                    item.get("stock_available"),
                    path + "/stock_available",
                    issues,
                    nonnegative=True,
                )
                if "stock_available" in item
                else MISSING
            )
            pack = (
                _parse_number(
                    item.get("pack_size"),
                    path + "/pack_size",
                    issues,
                    positive=True,
                )
                if "pack_size" in item
                else None
            )
            price = (
                _parse_number(
                    item.get("unit_price_minor"),
                    path + "/unit_price_minor",
                    issues,
                    nonnegative=True,
                )
                if "unit_price_minor" in item
                else None
            )
            fixed = (
                _parse_number(
                    item.get("fixed_cost_minor"),
                    path + "/fixed_cost_minor",
                    issues,
                    nonnegative=True,
                )
                if "fixed_cost_minor" in item
                else Fraction(0)
            )
            declared = (
                _parse_number(
                    item.get("declared_total_minor"),
                    path + "/declared_total_minor",
                    issues,
                    nonnegative=True,
                )
                if "declared_total_minor" in item
                else None
            )
            shortfall = None
            packs = None
            billed = None
            basis = "unknown"
            capacity_margin = None
            capacity_status = "not_applicable"
            if stock_role == "capacity":
                capacity_status = "unknown"
                if stock is MISSING:
                    _add_issue(
                        issues,
                        "pending",
                        "CAPACITY_UNKNOWN",
                        path + "/stock_available",
                        "Capacity availability is unknown, while gross consumption charges are still computed independently; zero/free capacity is not assumed.",
                    )
                elif stock is not None and quantity is not None:
                    capacity_margin = stock - quantity
                    if quantity <= stock:
                        capacity_status = "satisfied"
                    else:
                        capacity_status = "exceeded"
                        _add_issue(
                            issues,
                            "validation",
                            "CAPACITY_EXCEEDED",
                            path + "/stock_available",
                            "Required quantity exceeds the declared capacity; the capacity is not procurement stock and the quantity was not clipped.",
                        )
                if quantity is not None:
                    if pack is not None:
                        packs = _ceiling_fraction(quantity / pack)
                        billed = packs * pack
                        basis = "capacity_full_quantity_with_explicit_pack"
                    else:
                        billed = quantity
                        basis = "capacity_full_quantity_without_pack"
            elif stock_role == "none":
                if quantity is not None:
                    if pack is not None:
                        packs = _ceiling_fraction(quantity / pack)
                        billed = packs * pack
                        basis = "gross_full_quantity_no_stock_rule_with_explicit_pack"
                    else:
                        billed = quantity
                        basis = "gross_full_quantity_no_stock_rule_without_pack"
            else:
                if stock is MISSING:
                    _add_issue(
                        issues,
                        "pending",
                        "COST_STOCK_UNKNOWN",
                        path + "/stock_available",
                        "Stock is unknown: deficit remains unknown; zero stock is not assumed.",
                    )
                    if pack is None and quantity is not None:
                        billed = quantity
                        basis = "gross_due_to_unknown_stock_without_pack"
                    else:
                        basis = "net_of_unknown_stock_with_pack"
                elif stock is not None and quantity is not None:
                    shortfall = max(Fraction(0), quantity - stock)
                    if pack is not None:
                        packs = _ceiling_fraction(shortfall / pack)
                        billed = packs * pack
                        basis = "net_of_known_stock_with_explicit_pack"
                    else:
                        billed = shortfall
                        basis = "net_of_known_stock_without_pack"
            charge_quantity = billed
            item_cost = (
                billed * price
                if billed is not None and price is not None
                else None
            )
            pack_rounded_cost = (
                billed * price
                if stock_role == "purchase" and billed is not None and price is not None
                else None
            )
            if "unit_price_minor" not in item:
                _add_issue(
                    issues,
                    "pending",
                    "UNIT_PRICE_UNKNOWN",
                    path + "/unit_price_minor",
                    "The price is missing and is not guessed or treated as zero.",
                )
            declared_status = "not_provided"
            if declared is not None:
                if item_cost is None:
                    declared_status = "pending"
                elif declared == item_cost:
                    declared_status = "matched"
                else:
                    declared_status = "mismatched"
                    _add_issue(
                        issues,
                        "validation",
                        "DECLARED_ITEM_COST_MISMATCH",
                        path + "/declared_total_minor",
                        "The declared item total differs from billed_quantity*unit_price_minor using exact arithmetic; shortfall is diagnostic and is not substituted for the billed pack quantity.",
                    )
            item_report = {
                "id": item_id,
                "quantity": _fraction_text(quantity),
                "unit": unit if isinstance(unit, str) else None,
                "stock_available": None if stock is MISSING else _fraction_text(stock),
                "stock_status": "not_applicable" if stock_role == "none" else ("unknown" if stock is MISSING else "known"),
                "stock_role": stock_role,
                "stock_role_status": stock_role_status,
                "capacity": _fraction_text(stock) if stock_role == "capacity" and stock is not MISSING else None,
                "capacity_margin": _fraction_text(capacity_margin),
                "capacity_status": capacity_status,
                "capacity_margin_basis": "capacity - quantity in the declared cost-item unit; arithmetic only",
                "capacity_measurement_source": "source on this cost item; locator/raw/integrity checks do not prove semantic support",
                "shortfall": _fraction_text(shortfall),
                "deficit_status": "not_applicable" if stock_role in ("capacity", "none") else ("unknown" if shortfall is None else "known"),
                "pack_size": _fraction_text(pack),
                "packs": packs,
                "billed_quantity": _fraction_text(billed),
                "charge_quantity": _fraction_text(charge_quantity),
                "billing_basis": basis,
                "unit_price_minor": _fraction_text(price),
                "item_cost_minor": _fraction_text(item_cost),
                "item_cost_status": "known" if item_cost is not None else "unknown",
                "gross_price_status": "complete" if item_cost is not None else "unknown",
                "pack_rounded_gross_cost_minor": _fraction_text(pack_rounded_cost),
                "fixed_cost_minor": _fraction_text(fixed),
                "declared_total_minor": _fraction_text(declared),
                "declared_total_status": declared_status,
                "currency": currency,
                "source": source_report,
            }
            report["items"].append(item_report)
            if currency:
                group = groups.setdefault(
                    currency,
                    {
                        "item_cost_known_minor": Fraction(0),
                        "fixed_cost_known_minor": Fraction(0),
                        "total_known_minor": Fraction(0),
                        "complete": True,
                        "unknown_item_ids": [],
                    },
                )
                if stock is MISSING and stock_role not in ("capacity", "none"):
                    group["complete"] = False
                    group["unknown_item_ids"].append(item_id)
                if item_cost is None:
                    group["complete"] = False
                    if item_id not in group["unknown_item_ids"]:
                        group["unknown_item_ids"].append(item_id)
                else:
                    group["item_cost_known_minor"] += item_cost
                if fixed is None:
                    group["complete"] = False
                    if item_id not in group["unknown_item_ids"]:
                        group["unknown_item_ids"].append(item_id)
                else:
                    group["fixed_cost_known_minor"] += fixed
        for currency, group in groups.items():
            group["total_known_minor"] = (
                group["item_cost_known_minor"] + group["fixed_cost_known_minor"]
            )
            report["currencies"][currency] = {
                "item_cost_known_minor": _fraction_text(group["item_cost_known_minor"]),
                "fixed_cost_known_minor": _fraction_text(group["fixed_cost_known_minor"]),
                "total_known_minor": _fraction_text(group["total_known_minor"]),
                "cost_status": "complete" if group["complete"] else "partial",
                "unknown_item_ids": group["unknown_item_ids"],
            }

        declared_values = {}
        scalar_declared = candidate.get("declared_total_minor", MISSING)
        if scalar_declared is not MISSING:
            if isinstance(scalar_declared, dict):
                for currency, value in scalar_declared.items():
                    declared_values[currency] = (value, "/declared_total_minor/" + str(currency))
            else:
                declared_values[None] = (scalar_declared, "/declared_total_minor")
        mapped_declared = candidate.get("declared_totals_minor", MISSING)
        if mapped_declared is not MISSING:
            if not isinstance(mapped_declared, dict):
                _add_issue(
                    issues,
                    "structural",
                    "DECLARED_TOTALS_OBJECT_REQUIRED",
                    candidate_path + "/declared_totals_minor",
                    "declared_totals_minor must map currency identifiers to exact numeric strings.",
                )
            else:
                for currency, value in mapped_declared.items():
                    suffix = "/declared_totals_minor/" + str(currency)
                    if currency in declared_values:
                        _add_issue(
                            issues,
                            "structural",
                            "DUPLICATE_DECLARED_CURRENCY_TOTAL",
                            candidate_path + suffix,
                            "A currency total was supplied through both aggregate fields; use only one to avoid ambiguity.",
                        )
                    declared_values[currency] = (value, suffix)
        budget_currency = candidate.get("budget_currency")
        scalar_currency = None
        if isinstance(budget_currency, str) and budget_currency:
            scalar_currency = budget_currency
        elif len(groups) == 1:
            scalar_currency = next(iter(groups))
        for declared_currency, (value, suffix) in declared_values.items():
            comparison_currency = declared_currency or scalar_currency
            path = candidate_path + suffix
            parsed = _parse_number(value, path, issues, nonnegative=True)
            comparison = {
                "currency": comparison_currency,
                "declared_total_minor": _fraction_text(parsed),
                "expected_total_known_minor": None,
                "status": "pending",
            }
            if comparison_currency is None:
                _add_issue(
                    issues,
                    "pending",
                    "DECLARED_TOTAL_CURRENCY_UNKNOWN",
                    path,
                    "A scalar candidate total needs one unambiguous currency; currencies are never assumed interchangeable.",
                )
            else:
                group = groups.get(comparison_currency)
                expected = group["total_known_minor"] if group else Fraction(0)
                complete = group["complete"] if group else True
                comparison["expected_total_known_minor"] = _fraction_text(expected)
                if not complete:
                    comparison["status"] = "pending"
                elif parsed == expected:
                    comparison["status"] = "matched"
                elif parsed is not None:
                    comparison["status"] = "mismatched"
                    _add_issue(
                        issues,
                        "validation",
                        "DECLARED_CANDIDATE_TOTAL_MISMATCH",
                        path,
                        "The declared candidate total differs from exact known item costs plus fixed charges for this currency.",
                    )
            report["declared_comparisons"].append(comparison)
        for currency in groups:
            if declared_values and not any(
                comparison["currency"] == currency for comparison in report["declared_comparisons"]
            ):
                _add_issue(
                    issues,
                    "validation",
                    "DECLARED_TOTAL_CURRENCY_MISSING",
                    candidate_path + "/declared_totals_minor",
                    "An aggregate declaration was supplied but omits a cost currency; no cross-currency netting is performed.",
                )

        if "budget_minor" not in candidate:
            report["budget"] = {"status": "not_provided"}
            return report
        budget = _parse_number(
            candidate.get("budget_minor"),
            candidate_path + "/budget_minor",
            issues,
            nonnegative=True,
        )
        currency = scalar_currency
        budget_report = {
            "budget_minor": _fraction_text(budget),
            "currency": currency,
            "total_known_plus_fixed_minor": None,
            "status": "pending",
        }
        if currency is None:
            _add_issue(
                issues,
                "pending",
                "BUDGET_CURRENCY_UNKNOWN",
                candidate_path + "/budget_minor",
                "A scalar budget is comparable only with one cost currency or an explicit budget_currency.",
            )
        else:
            group = groups.get(currency)
            total = group["total_known_minor"] if group else Fraction(0)
            complete = group["complete"] if group else True
            budget_report["total_known_plus_fixed_minor"] = _fraction_text(total)
            if budget is not None:
                if total > budget:
                    budget_report["status"] = "fail"
                    _add_issue(
                        issues,
                        "validation",
                        "BUDGET_EXCEEDED",
                        candidate_path + "/budget_minor",
                        "Known item costs plus fixed charges already exceed the budget; unknown lines cannot compensate.",
                    )
                elif complete:
                    budget_report["status"] = "pass" if total <= budget else "fail"
                else:
                    budget_report["status"] = "pending"
                    _add_issue(
                        issues,
                        "pending",
                        "BUDGET_COMPLETENESS_UNKNOWN",
                        candidate_path + "/budget_minor",
                        "At least one same-currency item cost or fixed charge is unknown, so full budget feasibility is not a pass.",
                    )
        report["budget"] = budget_report
        return report

    def _audit_task_sources(self, candidate, candidate_path, issues):
        tasks = candidate.get("tasks")
        reports = []
        if not isinstance(tasks, list):
            return reports
        identifiers = set()
        for index, task in enumerate(tasks):
            path = candidate_path + "/tasks/%d" % index
            if not isinstance(task, dict):
                _add_issue(
                    issues,
                    "structural",
                    "TASK_OBJECT_REQUIRED",
                    path,
                    "Each task must be an object.",
                )
                continue
            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id:
                _add_issue(
                    issues,
                    "structural",
                    "TASK_ID_REQUIRED",
                    path + "/id",
                    "A nonempty task id is required; scheduling fields remain owned by schedule.py.",
                )
                task_id = "task[%d]" % index
            elif task_id in identifiers:
                _add_issue(
                    issues,
                    "structural",
                    "DUPLICATE_TASK_ID",
                    path + "/id",
                    "Task ids must be unique within a candidate.",
                )
            identifiers.add(task_id)
            source_report, _ = self.sources.audit(task.get("source"), path + "/source", issues)
            reports.append({"id": task_id, "source": source_report})
        return reports

    def _audit_calendar_sources(self, candidate, candidate_path, issues):
        calendars = candidate.get("resource_calendars")
        reports = []
        if not isinstance(calendars, list):
            return reports
        for index, calendar in enumerate(calendars):
            if not isinstance(calendar, dict) or "source" not in calendar:
                continue
            path = candidate_path + "/resource_calendars/%d" % index
            resource_id = calendar.get("resource_id")
            if not isinstance(resource_id, str) or not resource_id:
                resource_id = "calendar[%d]" % index
            source_report, _ = self.sources.audit(
                calendar.get("source"), path + "/source", issues
            )
            reports.append({"resource_id": resource_id, "source": source_report})
        return reports

    def _audit_schedule(self, candidate, candidate_path, issues):
        tasks = candidate.get("tasks")
        if isinstance(tasks, list) and not tasks:
            return {"status": "not_applicable", "reason": "no_tasks", "tasks": [], "violations": []}
        try:
            from schedule import audit_schedule
        except (ImportError, ModuleNotFoundError):
            _add_issue(
                issues,
                "pending",
                "SCHEDULE_UNAVAILABLE",
                candidate_path + "/tasks",
                "Tasks are present but schedule.audit_schedule is unavailable; this is pending, never a skipped pass.",
            )
            return {
                "status": "pending",
                "reason": "schedule_unavailable",
                "tasks": [],
                "violations": [],
            }
        try:
            result = audit_schedule(candidate)
        except Exception as error:
            _add_issue(
                issues,
                "operational",
                "SCHEDULE_OPERATIONAL_ERROR",
                candidate_path + "/tasks",
                "The schedule implementation raised %s; source data and traceback are not embedded." % type(error).__name__,
            )
            return {
                "status": "error",
                "reason": "schedule_exception",
                "error_type": type(error).__name__,
                "tasks": [],
                "violations": [],
            }
        if not isinstance(result, dict):
            _add_issue(
                issues,
                "operational",
                "SCHEDULE_RESULT_INVALID",
                candidate_path + "/tasks",
                "audit_schedule must return an object containing status, tasks, and violations.",
            )
            return {"status": "error", "reason": "invalid_schedule_result", "tasks": [], "violations": []}
        report = _json_safe(result)
        raw_status = result.get("status")
        malformed_arrays = (
            ("tasks" in result and not isinstance(result.get("tasks"), list))
            or ("schedule" in result and not isinstance(result.get("schedule"), list))
            or ("violations" in result and not isinstance(result.get("violations"), list))
        )
        if isinstance(result.get("tasks"), list):
            task_rows = result["tasks"]
        elif isinstance(result.get("schedule"), list):
            task_rows = result["schedule"]
        else:
            task_rows = None
        if task_rows is not None:
            report["tasks"] = _json_safe(task_rows)
        bare_pass = str(raw_status).lower() in ("pass", "ok", "valid") and (
            task_rows is None or not isinstance(result.get("violations"), list)
        )
        if malformed_arrays or bare_pass:
            _add_issue(
                issues,
                "operational",
                "SCHEDULE_RESULT_INVALID",
                candidate_path + "/tasks",
                "Schedule arrays must be arrays when supplied, and a pass requires task rows (tasks or schedule) and violations arrays; pending/fail details may be scheduler-specific.",
            )
            report["returned_status"] = raw_status if isinstance(raw_status, (str, int, float, bool)) else None
            report["status"] = "error"
            report["reason"] = "missing_or_invalid_tasks_or_violations"
            report["tasks"] = _json_safe(task_rows) if task_rows is not None else []
            report["violations"] = result.get("violations") if isinstance(result.get("violations"), list) else []
            return report
        normalized = str(raw_status).lower() if raw_status is not None else "pending"
        if normalized in ("pass", "ok", "valid"):
            normalized = "pass"
        elif normalized in ("fail", "failed", "invalid", "infeasible"):
            normalized = "fail"
        elif normalized in ("error", "operational_error"):
            normalized = "error"
        elif normalized in ("skipped", "skip", "not_implemented", "unimplemented"):
            normalized = "pending"
            _add_issue(
                issues,
                "pending",
                "SCHEDULE_NOT_IMPLEMENTED",
                candidate_path + "/tasks",
                "The scheduler reported skipped/not implemented for a candidate with tasks; this cannot be promoted to pass.",
            )
        else:
            normalized = "pending"
        if "status" not in result:
            _add_issue(
                issues,
                "pending",
                "SCHEDULE_STATUS_MISSING",
                candidate_path + "/tasks",
                "The scheduler omitted status, so scheduling remains pending.",
            )
        report["returned_status"] = raw_status if isinstance(raw_status, (str, int, float, bool)) else None
        report["status"] = normalized
        violations = result.get("violations", [])
        if not isinstance(violations, list):
            _add_issue(
                issues,
                "operational",
                "SCHEDULE_VIOLATIONS_INVALID",
                candidate_path + "/tasks",
                "schedule violations must be an array when returned.",
            )
            violations = []
            report["violations"] = []
            normalized = "error"
        if violations and normalized == "pass":
            normalized = "fail"
            report["status"] = "fail"
            _add_issue(
                issues,
                "validation",
                "SCHEDULE_STATUS_INCONSISTENT",
                candidate_path + "/tasks",
                "A scheduler cannot return pass together with violations.",
            )
        elif normalized == "fail" and not any(
            issue["code"] == "SCHEDULE_STATUS_INCONSISTENT" for issue in issues
        ):
            _add_issue(
                issues,
                "validation",
                "SCHEDULE_VIOLATION",
                candidate_path + "/tasks",
                "The schedule auditor returned %d violation(s); see the preserved schedule report."
                % len(violations),
            )
        elif normalized == "pending" and not any(
            issue["code"] in ("SCHEDULE_NOT_IMPLEMENTED", "SCHEDULE_STATUS_MISSING")
            and issue["path"] == candidate_path + "/tasks"
            for issue in issues
        ):
            _add_issue(
                issues,
                "pending",
                "SCHEDULE_PENDING",
                candidate_path + "/tasks",
                "The scheduler did not establish a complete feasible schedule.",
            )
        elif normalized == "error":
            _add_issue(
                issues,
                "operational",
                "SCHEDULE_OPERATIONAL_ERROR",
                candidate_path + "/tasks",
                "The scheduler returned an operational error status.",
            )
        return report

    def _audit_horizon(self, candidate, schedule, candidate_path, issues):
        if "horizon_minutes" not in candidate:
            return {"status": "not_applicable"}
        horizon = _parse_number(
            candidate.get("horizon_minutes"),
            candidate_path + "/horizon_minutes",
            issues,
            nonnegative=True,
        )
        report = {
            "status": "error" if horizon is None else "pending",
            "horizon_minutes": _fraction_text(horizon),
            "time_basis": "numeric minutes from the common planning origin; every task end must be <= horizon_minutes",
        }
        if horizon is None:
            return report
        if schedule.get("status") == "not_applicable":
            report["status"] = "not_applicable"
            report["reason"] = "no_tasks"
            return report
        if schedule.get("status") != "pass":
            report["status"] = "not_checked"
            report["reason"] = "a complete valid schedule has not been established"
            return report
        task_rows = schedule.get("tasks")
        if not isinstance(task_rows, list):
            task_rows = schedule.get("schedule")
        if not isinstance(task_rows, list):
            _add_issue(
                issues,
                "pending",
                "HORIZON_TASKS_UNREADABLE",
                candidate_path + "/horizon_minutes",
                "The horizon cannot be verified without readable task end times.",
            )
            return report
        if not task_rows:
            report["status"] = "not_applicable"
            report["reason"] = "no_tasks"
            return report
        ends = []
        for index, task in enumerate(task_rows):
            end = task.get("end") if isinstance(task, dict) else None
            if not _is_numeric_string(end):
                _add_issue(
                    issues,
                    "pending",
                    "HORIZON_TIME_BASIS_MISMATCH",
                    candidate_path + "/horizon_minutes",
                    "A numeric horizon requires numeric end offsets with the same planning origin; use an explicit ISO per-task deadline instead of coercing an absolute timestamp.",
                )
                report["unreadable_task_index"] = index
                return report
            ends.append((Fraction(end), task))
        latest_end, _ = max(ends, key=lambda pair: pair[0])
        report["latest_end_minutes"] = _fraction_text(latest_end)
        exceeded = [
            {
                "task_id": task.get("task_id") or task.get("id"),
                "end": task.get("end"),
                "horizon_minutes": _fraction_text(horizon),
            }
            for end, task in ends
            if end > horizon
        ]
        report["violations"] = exceeded
        if exceeded:
            _add_issue(
                issues,
                "validation",
                "HORIZON_EXCEEDED",
                candidate_path + "/horizon_minutes",
                "At least one task ends after the declared planning-origin horizon; the horizon was not silently relaxed.",
            )
            report["status"] = "fail"
        else:
            report["status"] = "pass"
        return report

    def _audit_scientific(self, candidate, candidate_path, issues):
        checks = candidate.get("scientific_checks")
        reports = []
        pending_experts = []
        if not isinstance(checks, list):
            return reports, "pending", pending_experts
        if not checks:
            _add_issue(
                issues,
                "pending",
                "SCIENTIFIC_REVIEW_MISSING",
                candidate_path + "/scientific_checks",
                "No scientific review checks were supplied; scientific readiness remains unknown, not pass.",
                "scientific",
            )
            return reports, "pending", pending_experts
        identifiers = set()
        for index, check in enumerate(checks):
            path = candidate_path + "/scientific_checks/%d" % index
            if not isinstance(check, dict):
                _add_issue(
                    issues,
                    "structural",
                    "SCIENTIFIC_CHECK_OBJECT_REQUIRED",
                    path,
                    "Each scientific check must be an object.",
                    "scientific",
                )
                continue
            check_id = check.get("id")
            if not isinstance(check_id, str) or not check_id:
                _add_issue(
                    issues,
                    "structural",
                    "SCIENTIFIC_CHECK_ID_REQUIRED",
                    path + "/id",
                    "A nonempty scientific check id is required.",
                    "scientific",
                )
                check_id = "scientific[%d]" % index
            elif check_id in identifiers:
                _add_issue(
                    issues,
                    "structural",
                    "DUPLICATE_SCIENTIFIC_CHECK_ID",
                    path + "/id",
                    "Scientific check ids must be unique within a candidate.",
                    "scientific",
                )
            identifiers.add(check_id)
            declared = check.get("status")
            if declared not in ("pass", "fail", "unknown", "not_applicable"):
                _add_issue(
                    issues,
                    "structural",
                    "SCIENTIFIC_STATUS_INVALID",
                    path + "/status",
                    "Scientific status must be pass, fail, unknown, or not_applicable.",
                    "scientific",
                )
            claim = check.get("claim")
            reason = check.get("reason")
            if not isinstance(claim, str):
                _add_issue(
                    issues,
                    "structural",
                    "SCIENTIFIC_CLAIM_REQUIRED",
                    path + "/claim",
                    "A scientific check requires a claim string; an empty claim cannot support a declared pass.",
                    "scientific",
                )
            if not isinstance(reason, str):
                _add_issue(
                    issues,
                    "structural",
                    "SCIENTIFIC_REASON_REQUIRED",
                    path + "/reason",
                    "A scientific check requires a reason string.",
                    "scientific",
                )
            affected = check.get("affected_steps", [])
            if not isinstance(affected, list) or any(not isinstance(item, str) for item in affected):
                _add_issue(
                    issues,
                    "structural",
                    "AFFECTED_STEPS_INVALID",
                    path + "/affected_steps",
                    "affected_steps must be an array of step-reference strings when supplied.",
                    "scientific",
                )
                affected = []
            expert_role = check.get("expert_role")
            if expert_role is not None and (not isinstance(expert_role, str) or not expert_role):
                _add_issue(
                    issues,
                    "structural",
                    "EXPERT_ROLE_INVALID",
                    path + "/expert_role",
                    "expert_role must be a nonempty string when supplied.",
                    "scientific",
                )
                expert_role = None
            source_report = None
            if "source" in check:
                source_report, _ = self.sources.audit(
                    check.get("source"), path + "/source", issues, scope="scientific"
                )
            effective = declared if declared in ("pass", "fail", "unknown", "not_applicable") else "unknown"
            if declared == "pass":
                if not isinstance(claim, str) or not claim:
                    effective = "unknown"
                    _add_issue(
                        issues,
                        "pending",
                        "SCIENTIFIC_PASS_CLAIM_MISSING",
                        path + "/claim",
                        "A declared scientific pass without a substantive claim is downgraded to pending.",
                        "scientific",
                    )
                if source_report is None:
                    effective = "unknown"
                    _add_issue(
                        issues,
                        "pending",
                        "SCIENTIFIC_PASS_SOURCE_MISSING",
                        path + "/source",
                        "A declared scientific pass without source locator evidence is downgraded to pending, not machine-proved.",
                        "scientific",
                    )
                elif source_report["status"] != "pass":
                    effective = "unknown"
            elif declared == "not_applicable":
                if not isinstance(reason, str) or not reason:
                    _add_issue(
                        issues,
                        "structural",
                        "NOT_APPLICABLE_REASON_REQUIRED",
                        path + "/reason",
                        "not_applicable requires a nonempty reason.",
                        "scientific",
                    )
            elif declared in ("fail", "unknown"):
                if not isinstance(reason, str) or not reason:
                    _add_issue(
                        issues,
                        "pending" if declared == "unknown" else "structural",
                        "SCIENTIFIC_REASON_MISSING",
                        path + "/reason",
                        "Failure/uncertainty needs an explicit reason so missing inputs and expert follow-up are visible.",
                        "scientific",
                    )
            if effective in ("unknown", "fail") or declared == "unknown":
                pending_experts.append(
                    {
                        "check_id": check_id,
                        "expert_role": expert_role,
                        "reason": reason if isinstance(reason, str) else "Reason not supplied",
                        "affected_steps": affected,
                        "declared_status": declared,
                    }
                )
            reports.append(
                {
                    "id": check_id,
                    "declared_status": declared,
                    "effective_status": effective,
                    "claim": claim if isinstance(claim, str) else None,
                    "reason": reason if isinstance(reason, str) else None,
                    "affected_steps": affected,
                    "expert_role": expert_role,
                    "source": source_report,
                    "semantic_support": "not_independently_verified",
                }
            )
        statuses = [item["effective_status"] for item in reports]
        if "fail" in statuses:
            status = "fail"
        elif not statuses or "unknown" in statuses:
            status = "pending"
        elif all(item in ("pass", "not_applicable") for item in statuses):
            status = "pass"
        else:
            status = "pending"
        return reports, status, pending_experts

    def _audit_candidate_metrics(self, candidate, candidate_path, issues):
        metrics = candidate.get("metrics", {})
        if not isinstance(metrics, dict):
            _add_issue(
                issues,
                "structural",
                "METRICS_OBJECT_REQUIRED",
                candidate_path + "/metrics",
                "metrics must map names to string values; numeric normalization occurs only during ranking.",
                "ranking",
            )
            return {}
        result = {}
        for name, value in metrics.items():
            path = candidate_path + "/metrics/" + str(name)
            if not isinstance(value, str):
                _add_issue(
                    issues,
                    "structural",
                    "METRIC_STRING_REQUIRED",
                    path,
                    "Metric values must be strings; booleans and JSON numbers are not silently coerced.",
                    "ranking",
                )
                result[str(name)] = {"value": None, "numeric": None, "status": "invalid"}
            elif _is_numeric_string(value):
                result[str(name)] = {
                    "value": value,
                    "numeric": _fraction_text(Fraction(value)),
                    "status": "numeric",
                }
            else:
                result[str(name)] = {"value": value, "numeric": None, "status": "non_numeric"}
        return result

    def _validate_parent_links(self, candidates):
        current = {}
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            candidate_id = candidate.get("candidate_id")
            if isinstance(candidate_id, str) and candidate_id:
                current.setdefault(candidate_id, []).append(index)
        source = {}
        case_candidates = (
            self.case_document.get("candidates")
            if isinstance(self.case_document, dict)
            else None
        )
        if isinstance(case_candidates, list):
            for case_index, candidate in enumerate(case_candidates):
                if not isinstance(candidate, dict):
                    continue
                identifiers = {}
                for key in ("id", "version_id", "candidate_id"):
                    candidate_id = candidate.get(key)
                    if isinstance(candidate_id, str) and candidate_id:
                        identifiers.setdefault(candidate_id, key)
                for candidate_id, key in identifiers.items():
                    source.setdefault(candidate_id, []).append((case_index, key))

        def reject_parent(candidate_report, code, message):
            parent_path = candidate_report.pop("parent_path")
            _add_issue(
                candidate_report["issues"],
                "validation",
                code,
                parent_path,
                message,
            )
            if candidate_report["status"] != "error":
                candidate_report["status"] = "fail"
            candidate_report["machine_pass"] = False
            if candidate_report["machine_status"] in ("pass", "pending"):
                candidate_report["machine_status"] = "fail"

        for index, candidate_report in enumerate(self.report["candidates"]):
            parent = candidate_report.get("parent_id")
            if not parent:
                continue
            candidate_report["parent_path"] = "/candidates/%d/parent_id" % index
            reference = None
            if parent in current:
                matches = current[parent]
                if len(matches) != 1:
                    reject_parent(
                        candidate_report,
                        "PARENT_CANDIDATE_AMBIGUOUS",
                        "parent_id matches multiple current candidates; no parent was selected implicitly.",
                    )
                    continue
                input_path = self.report.get("input_path")
                reference = {
                    "scope": "current_candidates",
                    "path": os.path.realpath(input_path) if isinstance(input_path, str) else None,
                    "pointer": "/candidates/%d/candidate_id" % matches[0],
                }
            elif parent in source:
                matches = source[parent]
                if len(matches) != 1:
                    reject_parent(
                        candidate_report,
                        "PARENT_CANDIDATE_AMBIGUOUS",
                        "parent_id matches multiple candidates in case_document.candidates; no original plan was selected implicitly.",
                    )
                    continue
                case_index, key = matches[0]
                reference = {
                    "scope": "source_case",
                    "path": os.path.realpath(self.case_path) if self.case_path else None,
                    "pointer": "/candidates/%d/%s" % (case_index, key),
                }
            else:
                reject_parent(
                    candidate_report,
                    "PARENT_CANDIDATE_MISSING",
                    "parent_id must identify one current candidate or one case-document candidate by a nonempty string id/version_id/candidate_id; no parent plan was invented.",
                )
                continue
            candidate_report["parent_reference"] = reference
            del candidate_report["parent_path"]

    def _audit_search(self, candidates):
        result = {
            "requested": self.exhaustive,
            "search_complete": False,
            "scope": "finite parameter-domain coverage only; never a proof of scientific global optimality or infeasibility",
            "search_limit": self.search_limit,
            "truncated": False,
            "global_optimality_proven": False,
            "infeasibility_proven": False,
            "domain_ids": [],
            "reason": "not_requested",
        }
        if not self.exhaustive:
            return result
        if not candidates or len(self.internal_candidates) != len(candidates):
            _add_issue(
                self.search_issues,
                "pending",
                "SEARCH_NOT_EVALUABLE",
                "/candidates",
                "Exhaustive comparison requires structurally present candidates and parameters.",
                "search",
            )
            result["reason"] = "invalid_candidates"
            return result
        name_order = None
        signature = None
        for index, internal in self.internal_candidates.items():
            params = internal["parameters"]
            raw_parameters = internal["candidate"].get("parameters")
            if not isinstance(raw_parameters, list) or len(params) != len(raw_parameters) or any(
                item["domain"] is None or item["parsed_value"] is None for item in params
            ):
                _add_issue(
                    self.search_issues,
                    "pending",
                    "SEARCH_NOT_EVALUABLE",
                    "/candidates/%d/parameters" % index,
                    "Exhaustive coverage is unavailable until every parameter value and finite domain is structurally valid.",
                    "search",
                )
                result["reason"] = "invalid_domains_or_values"
                return result
            names = [item["name"] for item in params]
            if len(set(names)) != len(names):
                result["reason"] = "duplicate_parameter_names"
                return result
            ordered = sorted(names)
            domains_by_name = {item["name"]: item for item in params}
            current_signature = {
                name: self._domain_signature(domains_by_name[name]) for name in ordered
            }
            if name_order is None:
                name_order = ordered
                signature = current_signature
            elif ordered != name_order or current_signature != signature:
                _add_issue(
                    self.search_issues,
                    "validation",
                    "SEARCH_DOMAIN_MISMATCH",
                    "/candidates/%d/parameters" % index,
                    "Exhaustive comparison requires consistent parameter names, units, and complete domain definitions across candidates.",
                    "search",
                )
                result["reason"] = "inconsistent_domains"
                return result
        if name_order is None:
            name_order = []
            signature = {}
        result["domain_ids"] = sorted(
            item["domain_id"]
            for internal in self.internal_candidates.values()
            for item in internal["parameters"]
        )
        first_domains = {
            item["name"]: item["domain"]
            for item in self.internal_candidates[0]["parameters"]
        }
        product_size = 1
        for name in name_order:
            domain = first_domains[name]
            if domain["kind"] == "interval":
                domain_size = self._interval_count(
                    domain["min"], domain["max"], domain["origin"], domain["step"]
                )
            else:
                domain_size = len(domain["allowed"])
            product_size *= domain_size
        if product_size > self.search_limit:
            result.update(
                {
                    "reason": "search_limit_exceeded",
                    "cartesian_size": product_size,
                    "truncated": True,
                    "search_complete": False,
                }
            )
            _add_issue(
                self.search_issues,
                "pending",
                "SEARCH_LIMIT_EXCEEDED",
                "/candidates",
                "The finite Cartesian product exceeds --search-limit; coverage is explicitly truncated and implies no infeasibility or optimality proof.",
                "search",
            )
            return result
        observed = {}
        duplicates = []
        for index, internal in self.internal_candidates.items():
            params = {item["name"]: item for item in internal["parameters"]}
            assignment = self._assignment_key(params, name_order)
            if assignment in observed:
                duplicates.append([observed[assignment], internal["id"]])
            else:
                observed[assignment] = internal["id"]
        domain_values = []
        if product_size:
            for name in name_order:
                values = self._enumerate_domain(first_domains[name])
                if values is None:
                    _add_issue(
                        self.search_issues,
                        "pending",
                        "SEARCH_DOMAIN_NOT_ENUMERABLE",
                        "/candidates/0/parameters",
                        "A domain could not be enumerated exactly; no categorical values were cloned or invented.",
                        "search",
                    )
                    result["reason"] = "non_enumerable_domain"
                    return result
                domain_values.append(values)
        expected = set()
        for combination in itertools.product(*domain_values):
            assignment = json.dumps(
                [[name, value[0], value[1]] for name, value in zip(name_order, combination)],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            expected.add(assignment)
        missing = sorted(expected - set(observed))
        extra = sorted(set(observed) - expected)
        result.update(
            {
                "cartesian_size": product_size,
                "unique_supplied_assignments": len(observed),
                "duplicate_assignments": duplicates,
                "missing_count": len(missing),
                "extra_count": len(extra),
                "missing_examples": [json.loads(item) for item in missing[:20]],
                "extra_examples": [json.loads(item) for item in extra[:20]],
                "search_complete": not missing and not extra,
                "reason": "complete" if not missing and not extra else "assignment_set_differs",
            }
        )
        if missing or extra:
            _add_issue(
                self.search_issues,
                "validation",
                "SEARCH_INCOMPLETE",
                "/candidates",
                "The supplied parameter assignment set differs from the bounded full Cartesian product; no replacement assignments were generated.",
                "search",
            )
        return result

    def _domain_signature(self, parameter):
        domain = parameter["domain"]
        if domain is None:
            return None
        if domain["kind"] == "interval":
            return {
                "kind": "interval",
                "min": _fraction_text(domain["min"]),
                "max": _fraction_text(domain["max"]),
                "origin": _fraction_text(domain["origin"]),
                "step": _fraction_text(domain["step"]),
                "unit": parameter["unit"],
            }
        return {
            "kind": domain["kind"],
            "allowed": [
                _fraction_text(value) if isinstance(value, Fraction) else value
                for value in domain["allowed"]
            ],
            "unit": parameter["unit"],
        }

    def _enumerate_domain(self, domain):
        if domain["kind"] == "interval":
            lower, upper = self._interval_bounds(
                domain["min"], domain["max"], domain["origin"], domain["step"]
            )
            if upper < lower:
                return []
            return [
                ("numeric", _fraction_text(domain["origin"] + index * domain["step"]))
                for index in range(lower, upper + 1)
            ]
        return [
            (
                "numeric" if isinstance(value, Fraction) else "categorical",
                _fraction_text(value) if isinstance(value, Fraction) else value,
            )
            for value in domain["allowed"]
        ]

    @staticmethod
    def _assignment_key(parameters, names):
        values = []
        for name in names:
            parameter = parameters[name]
            value = parameter["parsed_value"]
            kind = "numeric" if isinstance(value, Fraction) else "categorical"
            canonical = _fraction_text(value) if isinstance(value, Fraction) else value
            values.append([name, kind, canonical])
        return json.dumps(values, ensure_ascii=False, separators=(",", ":"))

    def _audit_ranking(self):
        priority = self.document.get("priority", []) if isinstance(self.document, dict) else []
        result = {
            "priority": _json_safe(priority) if isinstance(priority, list) else [],
            "status": "not_requested" if not priority else "pending",
            "eligible_ids": [],
            "unrankable_ids": [],
            "excluded_ids": [],
            "pareto_ids": [],
            "method": "Exact Pareto non-domination over eligible candidates only; no weights, fill-down, or zero substitution.",
        }
        if not isinstance(priority, list) or not priority:
            return result
        normalized_priority = []
        seen = set()
        for index, item in enumerate(priority):
            path = "/priority/%d" % index
            if not isinstance(item, dict):
                _add_issue(
                    self.ranking_issues,
                    "structural",
                    "PRIORITY_OBJECT_REQUIRED",
                    path,
                    "Each priority must be a metric/direction object.",
                    "ranking",
                )
                continue
            metric = item.get("metric")
            direction = item.get("direction")
            if not isinstance(metric, str) or not metric or direction not in ("min", "max"):
                _add_issue(
                    self.ranking_issues,
                    "structural",
                    "PRIORITY_INVALID",
                    path,
                    "Priority metric must be nonempty and direction must be min or max.",
                    "ranking",
                )
                continue
            if metric in seen:
                _add_issue(
                    self.ranking_issues,
                    "structural",
                    "DUPLICATE_PRIORITY_METRIC",
                    path + "/metric",
                    "A metric cannot appear more than once in the Pareto priority list.",
                    "ranking",
                )
                continue
            seen.add(metric)
            normalized_priority.append((metric, direction))
        values = {}
        for candidate in self.report["candidates"]:
            candidate_id = candidate["candidate_id"]
            if candidate["status"] != "pass" or not candidate["machine_pass"] or candidate["scientific_readiness"] != "pass":
                result["excluded_ids"].append(candidate_id)
                continue
            result["eligible_ids"].append(candidate_id)
            candidate_values = []
            rankable = True
            metrics = candidate.get("metrics", {})
            for metric, direction in normalized_priority:
                metric_report = metrics.get(metric)
                if not metric_report or metric_report.get("status") != "numeric":
                    rankable = False
                    _add_issue(
                        self.ranking_issues,
                        "pending",
                        "PRIORITY_METRIC_UNRANKABLE",
                        "/candidates/%s/metrics/%s" % (candidate_id, metric),
                        "An eligible candidate has a missing or nonnumeric priority metric; it is unrankable and is not assigned zero.",
                        "ranking",
                    )
                    break
                candidate_values.append((Fraction(metric_report["numeric"]), direction, metric))
            if not rankable:
                result["unrankable_ids"].append(candidate_id)
            else:
                values[candidate_id] = candidate_values
        for candidate_id, candidate_values in values.items():
            dominated = False
            for other_id, other_values in values.items():
                if other_id == candidate_id:
                    continue
                no_worse = True
                strictly_better = False
                for (left, direction, metric), (right, _, _) in zip(candidate_values, other_values):
                    better = right < left if direction == "min" else right > left
                    worse = right > left if direction == "min" else right < left
                    if worse:
                        no_worse = False
                        break
                    if better:
                        strictly_better = True
                if no_worse and strictly_better:
                    dominated = True
                    break
            if not dominated:
                result["pareto_ids"].append(candidate_id)
        result["pareto_ids"].sort()
        result["ranked_values"] = {
            candidate_id: {
                metric: _fraction_text(value) for value, direction, metric in candidate_values
            }
            for candidate_id, candidate_values in values.items()
        }
        if self.ranking_issues or result["unrankable_ids"]:
            result["status"] = "pending"
        else:
            result["status"] = "pass"
        return result

    def _all_issues(self):
        issues = list(self.input_issues) + self.search_issues + self.ranking_issues
        for candidate in self.report["candidates"]:
            issues.extend(candidate.get("issues", []))
        return issues

    def _finish(self):
        self.report["candidate_status_counts"] = {"pass": 0, "fail": 0, "pending": 0, "error": 0}
        counts = {"structural": 0, "operational": 0, "validation": 0, "pending": 0}
        for candidate in self.report["candidates"]:
            status = candidate.get("status", "error")
            if status not in self.report["candidate_status_counts"]:
                status = "error"
            self.report["candidate_status_counts"][status] += 1
        issues = self._all_issues()
        for issue in issues:
            counts[issue["kind"]] += 1
        counts["total"] = len(issues)
        self.report["issue_counts"] = counts
        self.report["search_issues"] = self.search_issues
        self.report["ranking_issues"] = self.ranking_issues
        if counts["structural"] or counts["operational"]:
            self.report["status"] = "error"
            self.report["exit_code"] = 1
        elif counts["validation"]:
            self.report["status"] = "fail"
            self.report["exit_code"] = 2
        elif counts["pending"]:
            self.report["status"] = "pending"
            self.report["exit_code"] = 2
        else:
            self.report["status"] = "pass"
            self.report["exit_code"] = 0


def _summary_issues(issues, pending_only=False):
    result = []
    seen = set()
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict) or (pending_only and issue.get("kind") != "pending"):
            continue
        key = (
            issue.get("kind"),
            issue.get("scope"),
            issue.get("code"),
            issue.get("path"),
        )
        if key in seen:
            continue
        seen.add(key)
        compact = {
            "kind": issue.get("kind"),
            "scope": issue.get("scope"),
            "code": issue.get("code"),
            "path": issue.get("path"),
        }
        if pending_only:
            compact["message"] = issue.get("message")
        result.append(compact)
    return result


def _summary_source(source):
    if not isinstance(source, dict):
        return None
    if source.get("status") == "pass":
        return "pass"
    return {
        key: _json_safe(source.get(key))
        for key in ("file", "pointer", "page", "locator", "status", "raw_status", "integrity_status")
        if key in source
    }


def _summary_latest_end(schedule, horizon):
    latest = horizon.get("latest_end_minutes") if isinstance(horizon, dict) else None
    if latest is not None:
        return latest
    task_rows = schedule.get("tasks")
    if not isinstance(task_rows, list):
        task_rows = schedule.get("schedule")
    if not isinstance(task_rows, list) or not task_rows:
        return None
    ends = []
    for task in task_rows:
        end = task.get("end") if isinstance(task, dict) else None
        if not _is_numeric_string(end):
            return None
        ends.append(Fraction(end))
    return _fraction_text(max(ends))


def _summary_schedule(schedule):
    if not isinstance(schedule, dict):
        return {"status": "unknown", "latest_end_minutes": None, "violations": []}
    horizon = schedule.get("horizon_audit")
    if not isinstance(horizon, dict):
        horizon = {}
    result = {
        "status": schedule.get("status"),
        "latest_end_minutes": _summary_latest_end(schedule, horizon),
        "horizon_minutes": horizon.get("horizon_minutes"),
        "horizon_status": horizon.get("status"),
        "violations": [],
    }
    for key in ("makespan", "makespan_minutes"):
        if key in schedule:
            result[key] = _json_safe(schedule.get(key))
    for violation in schedule.get("violations", []):
        if isinstance(violation, dict):
            if violation.get("severity") == "info":
                continue
            result["violations"].append(
                {
                    key: _json_safe(violation.get(key))
                    for key in ("severity", "code", "task_id", "resource_id", "calendar_id", "path", "message")
                    if key in violation
                }
            )
        else:
            result["violations"].append({"message": _json_safe(violation)})
    return result


def _summary_cost(cost):
    if not isinstance(cost, dict):
        return {"currencies": {}, "budget": {"status": "unknown"}, "capacity_records": []}
    capacity_records = []
    for item in cost.get("items", []):
        if not isinstance(item, dict) or item.get("stock_role") != "capacity":
            continue
        source = item.get("source")
        source_status = source.get("status") if isinstance(source, dict) else None
        record = {
            "id": item.get("id"),
            "quantity": item.get("quantity"),
            "unit": item.get("unit"),
            "capacity": item.get("capacity"),
            "margin": item.get("capacity_margin"),
            "status": item.get("capacity_status"),
            "source": _summary_source(source),
            "billed": item.get("billed_quantity"),
            "cost_minor": item.get("item_cost_minor"),
            "cost_status": item.get("gross_price_status"),
        }
        if (
            item.get("capacity_status") != "satisfied"
            or item.get("gross_price_status") != "complete"
            or source_status != "pass"
        ):
            record["anomaly"] = True
        capacity_records.append(record)
    return {
        "currencies": _json_safe(cost.get("currencies", {})),
        "budget": _json_safe(cost.get("budget", {"status": "not_provided"})),
        "declared_comparisons": _json_safe(cost.get("declared_comparisons", [])),
        "capacity_records": capacity_records,
    }


def _build_summary_report(report):
    candidates = []
    for candidate in report.get("candidates", []):
        non_pass_checks = []
        for check in candidate.get("scientific_checks", []):
            if check.get("effective_status") == "pass":
                continue
            non_pass_checks.append(
                {
                    key: _json_safe(check.get(key))
                    for key in (
                        "id",
                        "declared_status",
                        "effective_status",
                        "reason",
                        "expert_role",
                        "affected_steps",
                    )
                    if key in check
                }
            )
        issues = candidate.get("issues", [])
        summary_candidate = {
            "candidate_id": candidate.get("candidate_id"),
            "parent_id": candidate.get("parent_id"),
            "status": candidate.get("status"),
            "machine_status": candidate.get("machine_status"),
            "machine_pass": candidate.get("machine_pass"),
            "scientific_readiness": candidate.get("scientific_readiness"),
            "non_pass_scientific_checks": non_pass_checks,
            "machine_issues": _summary_issues(
                [issue for issue in issues if issue.get("scope") == "machine"]
            ),
            "other_issues": _summary_issues(
                [issue for issue in issues if issue.get("scope") != "machine"]
            ),
            "cost": _summary_cost(candidate.get("cost", {})),
            "schedule": _summary_schedule(candidate.get("schedule", {})),
        }
        if "parent_reference" in candidate:
            summary_candidate["parent_reference"] = _json_safe(
                candidate["parent_reference"]
            )
        candidates.append(summary_candidate)
    search_keys = (
        "requested",
        "search_complete",
        "scope",
        "search_limit",
        "truncated",
        "global_optimality_proven",
        "infeasibility_proven",
        "reason",
        "cartesian_size",
        "unique_supplied_assignments",
        "missing_count",
        "extra_count",
    )
    search = {
        key: _json_safe(report.get("search", {}).get(key))
        for key in search_keys
        if key in report.get("search", {})
    }
    search["candidate_count"] = len(candidates)
    ranking = report.get("ranking", {})
    pending_inputs = _summary_issues([
        issue
        for section in ("input_issues", "search_issues", "ranking_issues")
        for issue in report.get(section, [])
        if issue.get("kind") == "pending"
    ])
    return {
        "schema_version": "weekly-skill.plan-audit/v2.summary",
        "full_report_schema": report.get("schema_version"),
        "engine_version": ENGINE_VERSION,
        "case_id": report.get("case_id"),
        "example_notice": report.get("example_notice"),
        "report_status": report.get("status"),
        "report_exit_code": report.get("exit_code"),
        "scientific_or_safety_approval": False,
        "summary_scope": "Compact v2 navigation only: full values and source details remain in the full report. Candidate pending issues stay under that candidate; top pending_inputs covers only input/search/ranking. Informational schedule rows are omitted, while fail/unknown details are preserved.",
        "candidate_status_counts": _json_safe(report.get("candidate_status_counts", {})),
        "issue_counts": _json_safe(report.get("issue_counts", {})),
        "candidates": candidates,
        "input_issues": _summary_issues(report.get("input_issues", [])),
        "search": search,
        "search_issues": _summary_issues(report.get("search_issues", [])),
        "ranking": {
            key: _json_safe(ranking.get(key))
            for key in ("status", "eligible_ids", "unrankable_ids", "excluded_ids", "pareto_ids")
            if key in ranking
        },
        "ranking_issues": _summary_issues(report.get("ranking_issues", [])),
        "pending_expert_roles": _json_safe(report.get("pending_expert_roles", [])),
        "pending_inputs": _json_safe(pending_inputs),
    }


def _parser():
    parser = argparse.ArgumentParser(
        prog="plan_audit.py",
        description="Validate the normalized plan-audit IR with exact arithmetic; this is not the case output contract.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="Audit supplied finite candidates without generating replacements.")
    audit.add_argument("--input", required=True, help="Normalized audit JSON (read-only).")
    audit.add_argument("--output", required=True, help="Full validation JSON, written atomically.")
    audit.add_argument("--summary-output", help="Optional independent compact JSON for model review; never changes the full report, candidate status, or audit result.")
    audit.add_argument("--case", help="Actual case JSON, used for case_id and /input/case.json pointers (read-only).")
    audit.add_argument("--source-root", help="Root for legitimate relative local artifact paths; no network access.")
    audit.add_argument("--expected-candidates", type=int, help="Optionally require exactly N supplied candidates; no default count is invented.")
    audit.add_argument("--exhaustive", action="store_true", help="Compare assignments with the finite Cartesian product.")
    audit.add_argument("--search-limit", type=int, default=100000, help="Maximum Cartesian size (default: 100000).")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    initial_issues = []
    document = None
    case_document = None
    if args.expected_candidates is not None and args.expected_candidates < 0:
        initial_issues.append(
            {
                "kind": "structural",
                "scope": "input",
                "code": "EXPECTED_CANDIDATES_INVALID",
                "path": "/candidates",
                "message": "--expected-candidates cannot be negative.",
            }
        )
    if args.search_limit <= 0:
        initial_issues.append(
            {
                "kind": "structural",
                "scope": "search",
                "code": "SEARCH_LIMIT_INVALID",
                "path": "/candidates",
                "message": "--search-limit must be strictly positive.",
            }
        )
    try:
        document = _read_json(args.input)
    except Exception as error:
        initial_issues.append(
            {
                "kind": "operational",
                "scope": "input",
                "code": "AUDIT_INPUT_UNREADABLE",
                "path": "/",
                "message": "Could not read audit input (%s); no source payload or traceback is included." % type(error).__name__,
            }
        )
    if args.case:
        try:
            case_document = _read_json(args.case)
        except Exception as error:
            initial_issues.append(
                {
                    "kind": "operational",
                    "scope": "input",
                    "code": "CASE_INPUT_UNREADABLE",
                    "path": "/",
                    "message": "Could not read --case (%s); source pointers remain unresolved and no traceback is included." % type(error).__name__,
                }
            )
    if args.source_root and not os.path.isdir(args.source_root):
        initial_issues.append(
            {
                "kind": "operational",
                "scope": "input",
                "code": "SOURCE_ROOT_INVALID",
                "path": "/source_registry",
                "message": "--source-root must name an existing local directory.",
            }
        )
    auditor = PlanAuditor(
        document,
        case_document=case_document,
        case_path=args.case,
        source_root=args.source_root,
        expected_candidates=args.expected_candidates,
        exhaustive=args.exhaustive,
        search_limit=args.search_limit,
        initial_issues=initial_issues,
        input_path=args.input,
    )
    try:
        report = auditor.run()
    except Exception as error:
        auditor.input_issues.append(
            {
                "kind": "operational",
                "scope": "input",
                "code": "AUDIT_INTERNAL_ERROR",
                "path": "/",
                "message": "Audit execution stopped safely with %s. Partial actual status is preserved; no source payload or traceback is included." % type(error).__name__,
            }
        )
        auditor._finish()
        report = auditor.report
    report = _json_safe(report)
    try:
        _write_json_atomic(args.output, report)
    except Exception as error:
        sys.stderr.write(
            "plan_audit: could not write validation output (%s); no traceback/source payload emitted.\n"
            % type(error).__name__
        )
        return 1
    summary_written = False
    if args.summary_output:
        protected_paths = {
            os.path.realpath(args.output),
            os.path.realpath(args.input),
        }
        if args.case:
            protected_paths.add(os.path.realpath(args.case))
        if os.path.realpath(args.summary_output) in protected_paths:
            sys.stderr.write(
                "plan_audit: summary-output must differ from the full report, audit input, and case; the independent full report was preserved.\n"
            )
            return 1
        try:
            summary = _json_safe(_build_summary_report(report))
            _write_json_atomic(args.summary_output, summary, compact=True)
            summary_written = True
        except Exception as error:
            sys.stderr.write(
                "plan_audit: could not write summary output (%s); the independent full report was preserved and no traceback/source payload was emitted.\n"
                % type(error).__name__
            )
            return 1
    sys.stdout.write(
        "plan_audit: status=%s exit=%d candidates=%d output=%s\n"
        % (report.get("status"), report.get("exit_code", 1), len(report.get("candidates", [])), args.output)
    )
    if summary_written:
        sys.stdout.write("plan_audit: summary_output=%s\n" % args.summary_output)
    return int(report.get("exit_code", 1))


if __name__ == "__main__":
    sys.exit(main())
