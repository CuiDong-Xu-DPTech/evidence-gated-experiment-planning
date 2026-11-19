"""Explicit-path CLI for case skeletons, validation, snapshots, and change records."""

import argparse
import copy
import json
import os
import re
import sys

try:
    from . import runtime
except ImportError:
    import runtime


RUNTIME_FIELDS = ("status", "sources", "uncertainty", "change_records")
JSON_TYPES = {"null", "boolean", "object", "array", "number", "integer", "string"}
SCHEMA_ANNOTATIONS = {
    "$schema", "$id", "id", "$anchor", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly", "definitions", "$defs",
}
SUPPORTED_KEYWORDS = {
    "$ref", "type", "enum", "const", "required", "properties",
    "additionalProperties", "items", "minItems", "maxItems", "minLength",
    "maxLength", "minimum", "maximum",
}
MISSING = object()


class CommandError(Exception):
    def __init__(self, code, message, exit_code=1):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


class UsageError(CommandError):
    def __init__(self, message):
        super().__init__("invalid_arguments", message, 1)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _absolute(path):
    if not isinstance(path, str) or not path:
        raise UsageError("paths must be non-empty strings")
    return os.path.abspath(path)


def _pointer(tokens):
    if not tokens:
        return ""
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)


def _descriptor(path):
    return {"path": _absolute(path), "sha256": runtime.sha256_file(path)}


def _within(path, root):
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False


def find_output_contract(case):
    """Return (contract, pointer, matches, issue_code) for one recursive key match."""
    matches = []

    def visit(value, tokens):
        if isinstance(value, dict):
            for key in sorted(value):
                child_tokens = tokens + [key]
                if key == "output_contract":
                    matches.append((_pointer(child_tokens), value[key]))
                visit(value[key], child_tokens)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, tokens + [str(index)])

    visit(case, [])
    if not matches:
        return None, None, [], "missing_output_contract"
    if len(matches) != 1:
        return None, None, matches, "ambiguous_output_contract"
    return matches[0][1], matches[0][0], matches, None


def nested_schema_wrapper(contract, pointer):
    if not isinstance(contract, dict) or not isinstance(pointer, str):
        return contract, pointer, None
    candidate = contract.get("json_schema")
    if not isinstance(candidate, dict) or not _looks_like_schema(candidate):
        return contract, pointer, None
    artifact_paths = {
        key: value for key, value in contract.items()
        if key.endswith("_path") and isinstance(value, str) and value
    }
    if len(artifact_paths) < 2:
        return contract, pointer, None
    metadata = {key: copy.deepcopy(value) for key, value in contract.items() if key != "json_schema"}
    return candidate, pointer + "/json_schema", {
        "pointer": pointer,
        "metadata": metadata,
        "note": "Artifact path declarations are retained as wrapper metadata, not promoted to result fields.",
    }


def _named_field(descriptor):
    names = []
    for key in ("name", "key", "field"):
        if key in descriptor:
            if not isinstance(descriptor[key], str) or not descriptor[key]:
                return None, "field descriptor %s must be a non-empty string" % key
            names.append(descriptor[key])
    if not names:
        return None, "field descriptor has no name, key, or field"
    if any(name != names[0] for name in names[1:]):
        return None, "field descriptor has conflicting name/key/field values"
    return names[0], None


def _properties_from_list(fields, structural):
    properties = {}
    required = []
    for index, descriptor in enumerate(fields):
        required_field = False
        if isinstance(descriptor, str):
            name = descriptor
            schema = {}
        elif isinstance(descriptor, dict):
            name, problem = _named_field(descriptor)
            if problem:
                structural.append("fields/%d: %s" % (index, problem))
                continue
            required_field = descriptor.get("required") is True
            schema = _normalize_descriptor(descriptor, structural, field_descriptor=True)
        else:
            structural.append("fields/%d is neither a field name nor a descriptor" % index)
            continue
        if not name:
            structural.append("fields/%d has an empty field name" % index)
            continue
        if name in properties:
            structural.append("duplicate output field " + runtime.text(name, 120))
            continue
        properties[name] = schema
        if required_field:
            required.append(name)
    return properties, required


def _normalize_descriptor(descriptor, structural, field_descriptor=False):
    if isinstance(descriptor, str) and descriptor in JSON_TYPES:
        return {"type": descriptor}
    if not isinstance(descriptor, dict):
        return copy.deepcopy(descriptor)
    result = copy.deepcopy(descriptor)
    if field_descriptor:
        for key in ("name", "key", "field"):
            result.pop(key, None)
        if isinstance(result.get("required"), bool):
            result.pop("required")
    if "fields" in result and "properties" not in result and isinstance(result["fields"], list):
        properties, required = _properties_from_list(result["fields"], structural)
        result.pop("fields")
        result["properties"] = properties
        if required:
            existing = result.get("required", [])
            if isinstance(existing, list):
                result["required"] = sorted(set(existing + required))
    if isinstance(result.get("properties"), dict):
        result["properties"] = {
            key: _normalize_descriptor(value, structural)
            for key, value in result["properties"].items()
        }
    if isinstance(result.get("items"), (dict, str)):
        result["items"] = _normalize_descriptor(result["items"], structural)
    elif isinstance(result.get("items"), list):
        result["items"] = [
            _normalize_descriptor(item, structural) for item in result["items"]
        ]
    return result


def _looks_like_schema(contract):
    if "properties" in contract or "$ref" in contract:
        return True
    schema_keys = SUPPORTED_KEYWORDS - {"properties", "$ref"}
    if any(key in contract for key in ("oneOf", "anyOf", "allOf", "not", "if")):
        return True
    if "type" in contract:
        value = contract["type"]
        if isinstance(value, str) and value in JSON_TYPES:
            return True
        if isinstance(value, list):
            return True
    return bool(schema_keys.intersection(contract)) and not any(
        isinstance(value, dict) for value in contract.values()
    )


def adapt_contract(contract):
    """Return (schema, structural_errors, unsupported, form) without inventing fields."""
    structural = []
    unsupported = []
    if isinstance(contract, dict):
        if "fields" in contract and "properties" not in contract and isinstance(contract["fields"], list):
            properties, required = _properties_from_list(contract["fields"], structural)
            schema = {"type": "object", "properties": properties}
            declared_required = contract.get("required", [])
            if isinstance(declared_required, list) and all(
                isinstance(name, str) for name in declared_required
            ):
                required.extend(declared_required)
            if required:
                schema["required"] = sorted(set(required))
            if "additionalProperties" in contract:
                schema["additionalProperties"] = copy.deepcopy(contract["additionalProperties"])
            form = "fields_list"
        elif _looks_like_schema(contract):
            schema = _normalize_descriptor(contract, structural)
            form = "json_schema"
        elif not contract:
            schema = {"type": "object", "properties": {}}
            form = "field_mapping"
        else:
            properties = {}
            required = []
            for name in sorted(contract):
                if not isinstance(name, str) or not name:
                    structural.append("output field names must be non-empty strings")
                    continue
                descriptor = contract[name]
                properties[name] = _normalize_descriptor(descriptor, structural, field_descriptor=True)
                if isinstance(descriptor, dict) and descriptor.get("required") is True:
                    required.append(name)
            schema = {"type": "object", "properties": properties}
            if required:
                schema["required"] = sorted(required)
            form = "field_mapping"
        return schema, structural, unsupported, form
    if isinstance(contract, list):
        properties, required = _properties_from_list(contract, structural)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema, structural, unsupported, "field_list"
    return None, [], ["output_contract is prose or an unsupported non-object form"], "unknown"


def _declared_types(schema):
    kind = schema.get("type") if isinstance(schema, dict) else None
    if isinstance(kind, str):
        return [kind]
    if isinstance(kind, list):
        return [item for item in kind if isinstance(item, str)]
    if isinstance(schema, dict) and isinstance(schema.get("properties"), dict):
        return ["object"]
    return []


def _allows_value(schema, value, root_schema, active=None):
    """Conservative check used only to place honest runtime metadata."""
    if schema is True or schema is None:
        return True
    if schema is False:
        return False
    if not isinstance(schema, dict):
        return False
    if active is None:
        active = set()
    if "$ref" in schema and isinstance(schema["$ref"], str):
        reference = schema["$ref"]
        if reference in active:
            return False
        try:
            target = _local_reference(root_schema, reference)
        except CommandError:
            return False
        active = set(active)
        active.add(reference)
        return _allows_value(target, value, root_schema, active)
    if "const" in schema and not runtime.json_values_equal(schema["const"], value):
        return False
    if "enum" in schema and isinstance(schema["enum"], list):
        if not any(runtime.json_values_equal(option, value) for option in schema["enum"]):
            return False
    types = _declared_types(schema)
    if types and not any(_matches_type(value, kind) for kind in types):
        return False
    return True


def _local_reference(root_schema, reference):
    if reference == "#":
        return root_schema
    if isinstance(reference, str) and reference.startswith("#/"):
        try:
            return runtime.json_pointer_lookup(root_schema, reference[1:])
        except runtime.JsonPointerError:
            pass
    raise CommandError("invalid_schema_reference", "cannot resolve local schema reference", 2)


def _placeholder(schema, root_schema=None, active_refs=None):
    if schema is True:
        return None
    if schema is False or not isinstance(schema, (dict, list, str)) or schema is None:
        return None
    if isinstance(schema, str):
        return None
    if root_schema is None:
        root_schema = schema
    if active_refs is None:
        active_refs = set()
    if "$ref" in schema and isinstance(schema["$ref"], str):
        reference = schema["$ref"]
        if reference in active_refs:
            return None
        try:
            target = _local_reference(root_schema, reference)
        except CommandError:
            return None
        refs = set(active_refs)
        refs.add(reference)
        combined = copy.deepcopy(target) if isinstance(target, dict) else {}
        if isinstance(target, dict):
            for key, value in schema.items():
                if key != "$ref":
                    combined[key] = value
            return _placeholder(combined, root_schema, refs)
        return _placeholder(target, root_schema, refs)
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    types = _declared_types(schema)
    if not types:
        return None
    if "null" in types:
        return None
    kind = types[0]
    if kind == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return {}
        return {
            name: _placeholder(properties[name], root_schema, active_refs)
            for name in sorted(properties)
        }
    if kind == "array":
        return []
    if kind == "string":
        return ""
    return None


def _runtime_schema(schema, name):
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if name in properties:
        return properties[name], True, False
    additional = schema.get("additionalProperties", True) if isinstance(schema, dict) else True
    if additional is False:
        return None, False, True
    if isinstance(additional, dict):
        return additional, True, False
    conventional = {"type": "string"} if name == "status" else {"type": "array"}
    return conventional, True, False


def _uncertainty_messages(case, contract_issue, structural, unsupported):
    messages = ["Initial contract skeleton does not establish scientific validity."]
    if not isinstance(case, dict) or "case_id" not in case or case.get("case_id") is None:
        messages.append("The input case has no non-null root case_id; result case_id is null.")
    if contract_issue == "missing_output_contract":
        messages.append("No output_contract was found; original output fields could not be constructed.")
    elif contract_issue == "ambiguous_output_contract":
        messages.append("Multiple output_contract keys were found; no contract was selected.")
    messages.extend(structural)
    messages.extend(unsupported)
    return messages


def build_partial(case, contract, contract_issue):
    """Build the best truthful partial result and its out-of-band runtime record."""
    schema = None
    structural = []
    unsupported = []
    form = "unknown"
    if contract_issue is None:
        schema, structural, unsupported, form = adapt_contract(contract)
    messages = _uncertainty_messages(case, contract_issue, structural, unsupported)
    result = {}
    omitted = []
    limitations = list(structural) + list(unsupported)

    if not isinstance(case, dict) or "case_id" not in case:
        case_id = None
    else:
        case_id = copy.deepcopy(case["case_id"])

    if isinstance(schema, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
            limitations.append("Contract properties are not an object; no property skeleton was inferred.")
        for name in sorted(properties):
            result[name] = _placeholder(properties[name], schema)
        for name in RUNTIME_FIELDS:
            field_schema, allowed, explicitly_omitted = _runtime_schema(schema, name)
            if not allowed:
                if explicitly_omitted:
                    omitted.append(name)
                continue
            if name == "status":
                if _allows_value(field_schema, "partial", schema):
                    value = "partial"
                else:
                    fallback_schema = copy.deepcopy(field_schema) if isinstance(field_schema, dict) else {}
                    fallback_schema.pop("const", None)
                    fallback_schema.pop("enum", None)
                    value = _placeholder(fallback_schema, schema)
                    limitations.append("The contract's status field cannot hold 'partial'; see sidecar status.")
            else:
                value = _placeholder(field_schema, schema)
                if _allows_value(field_schema, [], schema):
                    value = []
                elif name != "uncertainty":
                    limitations.append("The contract's %s field cannot hold an empty array." % name)
            if name == "uncertainty" and isinstance(value, list):
                item_schema = field_schema.get("items", {}) if isinstance(field_schema, dict) else {}
                if all(_allows_value(item_schema, message, schema) for message in messages):
                    value = list(messages)
                elif messages:
                    limitations.append("Uncertainty details are retained only in the sidecar because of item constraints.")
            result[name] = value
        if "case_id" not in properties and schema.get("additionalProperties") is False:
            limitations.append(
                "The mandatory platform case_id is not permitted by additionalProperties:false; schema validation will report this conflict."
            )
    else:
        result = {
            "status": "partial",
            "sources": [],
            "uncertainty": list(messages),
            "change_records": [],
        }
    result["case_id"] = case_id
    return result, {
        "case_id": copy.deepcopy(case_id),
        "status": "partial",
        "sources": [],
        "uncertainty": messages,
        "change_records": [],
        "omitted_result_fields": sorted(omitted),
        "limitations": limitations,
        "contract_form": form,
        "structural_errors": structural,
        "unsupported": unsupported,
    }


def _matches_type(value, kind):
    if kind == "null":
        return value is None
    if kind == "boolean":
        return type(value) is bool
    if kind == "object":
        return type(value) is dict
    if kind == "array":
        return type(value) is list
    if kind == "number":
        return type(value) in (int, float)
    if kind == "integer":
        return (type(value) is int) or (type(value) is float and value.is_integer())
    if kind == "string":
        return type(value) is str
    return False


def _type_name(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is dict:
        return "object"
    if type(value) is list:
        return "array"
    if type(value) is str:
        return "string"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    return type(value).__name__


def validate_schema(schema, instance, allow_partial=False):
    """Validate the supported JSON Schema subset and explicitly flag everything else."""
    result = {
        "errors": [],
        "warnings": [],
        "unsupported": [],
        "schema_errors": [],
    }

    def problem(path, code, message, placeholder=False):
        item = {"path": path, "code": code, "message": message}
        if allow_partial and placeholder:
            result["warnings"].append(item)
        else:
            result["errors"].append(item)

    def schema_problem(path, message):
        result["schema_errors"].append({"path": path, "message": message})

    def recurse(schema_node, value, instance_path, schema_path, active_refs):
        if schema_node is True:
            return
        if schema_node is False:
            problem(instance_path, "false_schema", "false schema rejects every value")
            return
        if not isinstance(schema_node, dict):
            schema_problem(schema_path, "schema node must be an object or boolean")
            return
        for key in sorted(schema_node):
            if key not in SUPPORTED_KEYWORDS and key not in SCHEMA_ANNOTATIONS:
                result["unsupported"].append({
                    "path": schema_path + "/" + key.replace("~", "~0").replace("/", "~1"),
                    "feature": key,
                })
        if "$ref" in schema_node:
            reference = schema_node["$ref"]
            if not isinstance(reference, str) or not (reference == "#" or reference.startswith("#/")):
                result["unsupported"].append({"path": schema_path + "/$ref", "feature": "external_or_invalid_$ref"})
            else:
                try:
                    target = _local_reference(root_schema, reference)
                except CommandError:
                    schema_problem(schema_path + "/$ref", "unresolvable local reference")
                    target = None
                if target is not None:
                    guard = (reference, instance_path)
                    if guard in active_refs:
                        result["unsupported"].append({
                            "path": schema_path + "/$ref", "feature": "recursive_reference_at_same_instance",
                        })
                    else:
                        recurse(target, value, instance_path, reference, active_refs | {guard})
        types = _declared_types(schema_node)
        if "type" in schema_node:
            raw_type = schema_node["type"]
            valid_declaration = (
                isinstance(raw_type, str) and raw_type in JSON_TYPES
            ) or (
                isinstance(raw_type, list) and bool(raw_type)
                and all(isinstance(kind, str) and kind in JSON_TYPES for kind in raw_type)
            )
            if not valid_declaration:
                schema_problem(schema_path + "/type", "invalid type declaration")
                types = []
            elif not any(_matches_type(value, kind) for kind in types):
                problem(
                    instance_path,
                    "type",
                    "expected %s, found %s" % ("/".join(types), _type_name(value)),
                    placeholder=value is None,
                )
                return
        if instance_path == "":
            instance_path = ""
        if "const" in schema_node and not runtime.json_values_equal(value, schema_node["const"]):
            problem(instance_path, "const", "value differs from const", placeholder=value in (None, "", [], {}))
        if "enum" in schema_node:
            options = schema_node["enum"]
            if not isinstance(options, list) or not options:
                schema_problem(schema_path + "/enum", "enum must be a non-empty array")
            elif not any(runtime.json_values_equal(value, option) for option in options):
                problem(instance_path, "enum", "value is not in enum", placeholder=value in (None, "", [], {}))
        if isinstance(value, dict):
            properties = schema_node.get("properties", {})
            if "properties" in schema_node and not isinstance(properties, dict):
                schema_problem(schema_path + "/properties", "properties must be an object")
                properties = {}
            if isinstance(properties, dict):
                for name in sorted(properties):
                    if name in value:
                        recurse(
                            properties[name], value[name],
                            instance_path + "/" + name.replace("~", "~0").replace("/", "~1"),
                            schema_path + "/properties/" + name.replace("~", "~0").replace("/", "~1"),
                            active_refs,
                        )
            if "required" in schema_node:
                required = schema_node["required"]
                if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
                    schema_problem(schema_path + "/required", "required must be an array of strings")
                else:
                    for name in sorted(set(required)):
                        if name not in value:
                            problem(instance_path, "required", "missing required property " + runtime.text(name, 120))
            if "additionalProperties" in schema_node:
                additional = schema_node["additionalProperties"]
                if isinstance(additional, dict):
                    for name in sorted(set(value) - set(properties) if isinstance(properties, dict) else set(value)):
                        recurse(
                            additional, value[name],
                            instance_path + "/" + name.replace("~", "~0").replace("/", "~1"),
                            schema_path + "/additionalProperties", active_refs,
                        )
                elif type(additional) is not bool:
                    result["unsupported"].append({
                        "path": schema_path + "/additionalProperties",
                        "feature": "non_boolean_additionalProperties",
                    })
                elif additional is False and isinstance(properties, dict):
                    for name in sorted(set(value) - set(properties)):
                        problem(
                            instance_path + "/" + name.replace("~", "~0").replace("/", "~1"),
                            "additionalProperties", "additional property is not allowed",
                        )
        elif "required" in schema_node or "properties" in schema_node or "additionalProperties" in schema_node:
            if not isinstance(schema_node.get("required", []), (list,)):
                schema_problem(schema_path + "/required", "required must be an array")
        if isinstance(value, list):
            if "items" in schema_node:
                items = schema_node["items"]
                if isinstance(items, list):
                    for index, item_schema in enumerate(items):
                        if index < len(value):
                            recurse(
                                item_schema, value[index],
                                "%s/%d" % (instance_path, index),
                                "%s/items/%d" % (schema_path, index), active_refs,
                            )
                elif isinstance(items, (dict, bool)):
                    for index, item in enumerate(value):
                        recurse(
                            items, item, "%s/%d" % (instance_path, index),
                            schema_path + "/items", active_refs,
                        )
                else:
                    schema_problem(schema_path + "/items", "items must be a schema or schema array")
            for keyword, comparison in (("minItems", lambda n, m: n >= m), ("maxItems", lambda n, m: n <= m)):
                if keyword in schema_node:
                    limit = schema_node[keyword]
                    if type(limit) is not int or limit < 0:
                        schema_problem(schema_path + "/" + keyword, keyword + " must be a non-negative integer")
                    elif not comparison(len(value), limit):
                        problem(
                            instance_path, keyword,
                            "array length %d violates %s=%d" % (len(value), keyword, limit),
                            placeholder=keyword == "minItems" and not value,
                        )
        if isinstance(value, str):
            for keyword, comparison in (("minLength", lambda n, m: n >= m), ("maxLength", lambda n, m: n <= m)):
                if keyword in schema_node:
                    limit = schema_node[keyword]
                    if type(limit) is not int or limit < 0:
                        schema_problem(schema_path + "/" + keyword, keyword + " must be a non-negative integer")
                    elif not comparison(len(value), limit):
                        problem(
                            instance_path, keyword,
                            "string length %d violates %s=%d" % (len(value), keyword, limit),
                            placeholder=keyword == "minLength" and value == "",
                        )
        if type(value) in (int, float):
            for keyword, comparison in (("minimum", lambda n, m: n >= m), ("maximum", lambda n, m: n <= m)):
                if keyword in schema_node:
                    limit = schema_node[keyword]
                    if type(limit) not in (int, float):
                        schema_problem(schema_path + "/" + keyword, keyword + " must be numeric")
                    elif not comparison(value, limit):
                        problem(instance_path, keyword, "number violates %s" % keyword)

    root_schema = schema
    recurse(schema, instance, "", "", set())
    if result["schema_errors"]:
        result["status"] = "invalid_schema"
    elif result["unsupported"]:
        result["status"] = "not_run"
        result["reason"] = "unsupported"
    elif result["errors"]:
        result["status"] = "failed"
    elif result["warnings"]:
        result["status"] = "partial"
    else:
        result["status"] = "passed"
    return result


def _emit(report):
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _error_report(command, error):
    return {
        "command": command,
        "status": "error",
        "error": {"code": error.code, "message": runtime.text(error.message, 500)},
    }


def command_init(args):
    case_path = _absolute(args.case)
    work = _absolute(args.work)
    result_path = _absolute(args.output)
    case = runtime.read_json(case_path)
    if not isinstance(case, dict):
        raise CommandError("invalid_case", "case root must be a JSON object", 2)
    contract, contract_pointer, matches, contract_issue = find_output_contract(case)
    contract, contract_pointer, nested_metadata = nested_schema_wrapper(contract, contract_pointer)
    result, sidecar = build_partial(case, contract, contract_issue)
    runtime.write_json_atomic(result_path, result)
    result_descriptor = _descriptor(result_path)
    os.makedirs(work, exist_ok=True)
    sidecar.update({
        "contract_path": contract_pointer,
        "contract_matches": [{"path": path} for path, unused in matches],
        "result": result_descriptor,
        "created_at": runtime.utc_now(),
    })
    if nested_metadata:
        sidecar["nested_contract"] = nested_metadata
    if args.task:
        sidecar["task"] = _descriptor(args.task)
    sidecar_path = os.path.join(work, "contract_report.json")
    runtime.write_json_atomic(sidecar_path, sidecar)
    report = {
        "command": "init",
        "status": "partial",
        "result": result_descriptor,
        "sidecar": _descriptor(sidecar_path),
        "case_id_copied": isinstance(case, dict) and case.get("case_id") is not None,
        "contract": {
            "status": contract_issue or "found",
            "path": contract_pointer,
            "form": sidecar["contract_form"],
        },
        "warnings": sidecar["limitations"],
    }
    if args.task:
        report["task"] = sidecar["task"]
    if contract_issue or sidecar["structural_errors"]:
        report["status"] = "error"
        report["error"] = {
            "code": contract_issue or "invalid_output_contract",
            "message": "best honest partial was written; the output contract needs correction",
        }
        return 2, report
    return 0, report


def _metadata_requirements(result, schema):
    errors = []
    if not isinstance(result, dict):
        return errors, []
    omitted = []
    for name in RUNTIME_FIELDS:
        field_schema, allowed, explicitly_omitted = _runtime_schema(schema or {}, name)
        if not allowed:
            if explicitly_omitted:
                omitted.append(name)
            continue
        if name not in result:
            errors.append({"path": "/" + name, "code": "runtime_field_missing", "message": "required runtime metadata is missing"})
            continue
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if name not in properties and not isinstance((schema or {}).get("additionalProperties"), dict):
            if name == "status" and not isinstance(result[name], str):
                errors.append({"path": "/status", "code": "runtime_field_type", "message": "status must be a string"})
            if name != "status" and not isinstance(result[name], list):
                errors.append({"path": "/" + name, "code": "runtime_field_type", "message": name + " must be an array"})
    return errors, omitted


def command_validate(args):
    case_path = _absolute(args.case)
    result_path = _absolute(args.result)
    result_hash = runtime.sha256_file(result_path)
    case = runtime.read_json(case_path)
    result = runtime.read_json(result_path)
    errors = []
    warnings = []

    if not isinstance(result, dict):
        errors.append({"path": "", "code": "result_root", "message": "result root must be an object"})
    if not isinstance(case, dict):
        errors.append({"path": "", "code": "case_root", "message": "case root must be an object"})
    expected_case_id = case.get("case_id") if isinstance(case, dict) else None
    if not isinstance(result, dict) or "case_id" not in result:
        errors.append({"path": "/case_id", "code": "case_id_missing", "message": "root case_id is missing"})
    elif not isinstance(case, dict) or "case_id" not in case or expected_case_id is None:
        item = {"path": "/case_id", "code": "case_id_unavailable", "message": "case has no non-null case_id; null is accepted only as partial"}
        if runtime.canonical_hash(result["case_id"]) != runtime.canonical_hash(None):
            errors.append({"path": "/case_id", "code": "case_id_mismatch", "message": "case_id must be null when the case has no non-null case_id"})
        elif args.allow_partial:
            warnings.append(item)
        else:
            errors.append(item)
    elif runtime.canonical_hash(result["case_id"]) != runtime.canonical_hash(expected_case_id):
        errors.append({"path": "/case_id", "code": "case_id_mismatch", "message": "result case_id does not exactly match case case_id"})

    contract, contract_pointer, matches, contract_issue = find_output_contract(case if isinstance(case, dict) else {})
    schema = None
    structural = []
    unsupported = []
    form = "unknown"
    omitted_metadata = []
    if contract_issue:
        errors.append({
            "path": contract_pointer or "",
            "code": contract_issue,
            "message": "exactly one output_contract is required",
        })
        validation = {
            "status": "not_run", "reason": contract_issue,
            "errors": [], "warnings": [], "unsupported": [], "schema_errors": [],
        }
    else:
        contract, contract_pointer, _ = nested_schema_wrapper(contract, contract_pointer)
        schema, structural, unsupported, form = adapt_contract(contract)
        if schema is None:
            validation = {
                "status": "not_run", "reason": "unsupported",
                "errors": [], "warnings": [], "unsupported": unsupported, "schema_errors": [],
            }
        else:
            validation = validate_schema(schema, result, args.allow_partial)
            validation["unsupported"].extend(unsupported)
            if unsupported and validation["status"] == "passed":
                validation["status"] = "not_run"
                validation["reason"] = "unsupported"
            if structural:
                validation["schema_errors"].extend(
                    {"path": contract_pointer or "", "message": item} for item in structural
                )
                validation["status"] = "invalid_schema"
        if isinstance(result, dict) and isinstance(schema, dict) and isinstance(schema.get("properties"), dict):
            for name in sorted(schema["properties"]):
                if name not in result:
                    errors.append({
                        "path": "/" + name.replace("~", "~0").replace("/", "~1"),
                        "code": "output_field_missing",
                        "message": "an original top-level output_contract field is missing",
                    })
        metadata_errors, omitted_metadata = _metadata_requirements(result, schema)
        errors.extend(metadata_errors)

    errors.extend(validation["errors"])
    warnings.extend(validation["warnings"])
    errors.extend({
        "path": contract_pointer or "", "code": "invalid_schema", "message": item["message"]
    } for item in validation.get("schema_errors", []))
    unsupported_items = validation.get("unsupported", [])
    if unsupported_items and not args.allow_partial:
        errors.append({
            "path": contract_pointer or "",
            "code": "validation_not_run",
            "message": "unsupported schema features prevent full validation; use --allow-partial only for a partial result",
        })
    elif unsupported_items:
        warnings.append({
            "path": contract_pointer or "", "code": "validation_not_run", "message": "full schema validation was not run for unsupported features",
        })

    status = "partial" if args.allow_partial else "complete"
    report = {
        "command": "validate",
        "status": status,
        "result": {"path": result_path, "sha256": result_hash},
        "contract": {"status": contract_issue or "found", "path": contract_pointer, "form": form},
        "validation": {
            "status": validation["status"],
            "unsupported": unsupported_items,
            "errors": errors,
            "warnings": warnings,
            "omitted_runtime_fields": omitted_metadata,
        },
    }
    code = 2 if errors else 0
    if code:
        report["status"] = "error"
        report["error"] = {"code": "validation_failed", "message": "result validation failed"}
    if args.output:
        runtime.write_json_atomic(_absolute(args.output), report)
    return code, report


def _candidate_parent(document):
    if not isinstance(document, dict):
        return {}
    found = {}
    for key in ("parent", "parent_id"):
        if key in document:
            found[key] = copy.deepcopy(document[key])
    return found


def command_diff(args):
    before_path = _absolute(args.before)
    after_path = _absolute(args.after)
    output_path = _absolute(args.output)
    before_hash = runtime.sha256_file(before_path)
    after_hash = runtime.sha256_file(after_path)
    before = runtime.read_json(before_path)
    after = runtime.read_json(after_path)
    operations = runtime.make_patch(before, after)
    runtime.verify_patch(before, after, operations)
    base = {"path": before_path, "sha256": before_hash}
    target = {"path": after_path, "sha256": after_hash}
    base.update(_candidate_parent(before))
    target.update(_candidate_parent(after))
    change = {
        "format": "rfc6902",
        "base": base,
        "after": target,
        "operations": operations,
    }
    if isinstance(after, dict) and "parent" in after:
        change["parent"] = copy.deepcopy(after["parent"])
    runtime.write_json_atomic(output_path, change)
    return 0, {
        "command": "diff",
        "status": "ok",
        "change": _descriptor(output_path),
        "operations": len(operations),
        "base_sha256": before_hash,
        "after_sha256": after_hash,
    }


def command_verify_diff(args):
    change_path = _absolute(args.change)
    change = runtime.read_json(change_path)
    if not isinstance(change, dict) or change.get("format") != "rfc6902":
        raise CommandError("invalid_change", "change must be an object with format rfc6902", 2)
    if not isinstance(change.get("operations"), list):
        raise CommandError("invalid_change", "change operations must be an array", 2)
    documents = {}
    actual_hashes = {}
    mismatches = []
    for label in ("base", "after"):
        descriptor = change.get(label)
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str) or not isinstance(descriptor.get("sha256"), str):
            raise CommandError("invalid_change", label + " needs path and sha256", 2)
        path = _absolute(descriptor["path"])
        actual = runtime.sha256_file(path)
        actual_hashes[label] = actual
        if actual != descriptor["sha256"]:
            mismatches.append({"document": label, "expected": descriptor["sha256"], "actual": actual})
        documents[label] = runtime.read_json(path)
    report = {
        "command": "verify-diff",
        "status": "ok",
        "change": {"path": change_path, "sha256": runtime.sha256_file(change_path)},
        "base_sha256": actual_hashes["base"],
        "after_sha256": actual_hashes["after"],
        "hash_mismatches": mismatches,
    }
    if mismatches:
        report["status"] = "error"
        report["error"] = {"code": "source_hash_mismatch", "message": "base or after bytes changed"}
        return 2, report
    try:
        runtime.verify_patch(documents["base"], documents["after"], change["operations"])
    except (runtime.JsonPatchError, runtime.JsonDataError) as exc:
        report["status"] = "error"
        report["error"] = {"code": "patch_verification_failed", "message": runtime.text(exc, 500)}
        return 2, report
    return 0, report


def _looks_like_file_reference(value, key_hint):
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate or len(candidate) > 4096 or "\n" in candidate or "\r" in candidate or "\x00" in candidate:
        return False
    if "://" in candidate or candidate.lower().startswith(("doi:", "urn:", "mailto:")):
        return False
    basename = candidate.replace("\\", "/").rsplit("/", 1)[-1]
    file_syntax = (
        "/" in candidate or "\\" in candidate or "." in basename[1:]
        or candidate.lower().endswith(".pdf")
    )
    return file_syntax or key_hint


def command_snapshot(args):
    case_path = _absolute(args.case)
    input_root = _absolute(args.input_root)
    work = _absolute(args.work)
    if not os.path.isdir(input_root):
        raise CommandError("input_root_missing", "input root is not a directory: " + runtime.text(input_root, 300), 1)
    case = runtime.read_json(case_path)
    case_hash = runtime.sha256_file(case_path)
    files = []
    skipped_symlinks = []
    real_files = {}

    def walk_error(error):
        raise error

    for current, directories, filenames in os.walk(input_root, topdown=True, followlinks=False, onerror=walk_error):
        directories.sort()
        filenames.sort()
        retained = []
        for directory in directories:
            path = os.path.join(current, directory)
            if os.path.islink(path):
                skipped_symlinks.append(os.path.relpath(path, input_root))
            elif _within(path, work):
                continue
            else:
                retained.append(directory)
        directories[:] = retained
        if _within(current, work):
            continue
        for filename in filenames:
            path = os.path.join(current, filename)
            relative = os.path.relpath(path, input_root)
            if os.path.islink(path):
                skipped_symlinks.append(relative)
                continue
            if not os.path.isfile(path):
                continue
            real = os.path.realpath(path)
            if not _within(real, input_root):
                skipped_symlinks.append(relative)
                continue
            entry = {
                "path": relative.replace(os.sep, "/"),
                "sha256": runtime.sha256_file(path),
                "size_bytes": os.path.getsize(path),
            }
            files.append(entry)
            real_files[real] = entry["path"]

    references = []
    unresolved = []

    def scan_references(value, tokens, key_hint=False, label_value=False):
        if isinstance(value, dict):
            for key in sorted(value):
                lowered = key.lower()
                normalized = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
                hint = any(word in lowered for word in ("path", "file", "material", "attachment", "artifact", "document"))
                is_label = not hint and (
                    normalized in {"label", "title", "name", "caption", "description", "id", "case_id"}
                    or normalized.endswith(("_label", "_title", "_name", "_caption", "_description"))
                )
                scan_references(value[key], tokens + [key], hint, is_label)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                scan_references(item, tokens + [str(index)], key_hint, label_value)
        elif not label_value and _looks_like_file_reference(value, key_hint):
            provided = value
            candidate = value.strip()
            candidates = [candidate] if os.path.isabs(candidate) else [
                os.path.join(input_root, candidate), os.path.join(os.path.dirname(case_path), candidate)
            ]
            resolved = None
            for possible in candidates:
                real = os.path.realpath(possible)
                if _within(real, input_root) and real in real_files:
                    resolved = real
                    break
            record = {"case_pointer": _pointer(tokens), "provided_path": provided}
            if resolved is None:
                if any(character in candidate for character in ("/", "\\")) or "." in candidate.rsplit("/", 1)[-1][1:]:
                    unresolved.append(record)
            else:
                record["path"] = real_files[resolved]
                record["sha256"] = next(item["sha256"] for item in files if item["path"] == real_files[resolved])
                references.append(record)

    scan_references(case, [])
    snapshot = {
        "case": {"path": case_path, "sha256": case_hash},
        "input_root": input_root,
        "files": files,
        "case_references": references,
        "unresolved_file_references": unresolved,
        "skipped_symlinks": sorted(skipped_symlinks),
    }
    os.makedirs(work, exist_ok=True)
    output_path = os.path.join(work, "input_snapshot.json")
    runtime.write_json_atomic(output_path, snapshot)
    return 0, {
        "command": "snapshot",
        "status": "ok",
        "snapshot": _descriptor(output_path),
        "files": len(files),
        "case_references": len(references),
        "unresolved_file_references": len(unresolved),
        "skipped_symlinks": len(skipped_symlinks),
    }


def build_parser():
    parser = JsonArgumentParser(prog="case_io.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--case", required=True)
    init.add_argument("--work", required=True)
    init.add_argument("--output", required=True)
    init.add_argument("--task")
    init.set_defaults(handler=command_init)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--case", required=True)
    validate.add_argument("--result", required=True)
    validate.add_argument("--allow-partial", action="store_true")
    validate.add_argument("--output")
    validate.set_defaults(handler=command_validate)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--case", required=True)
    snapshot.add_argument("--input-root", required=True)
    snapshot.add_argument("--work", required=True)
    snapshot.set_defaults(handler=command_snapshot)
    diff = subparsers.add_parser("diff")
    diff.add_argument("--before", required=True)
    diff.add_argument("--after", required=True)
    diff.add_argument("--output", required=True)
    diff.set_defaults(handler=command_diff)
    verify = subparsers.add_parser("verify-diff")
    verify.add_argument("--change", required=True)
    verify.set_defaults(handler=command_verify_diff)
    return parser


def main(argv=None):
    parser = build_parser()
    command_name = argv[0] if argv else (sys.argv[1] if len(sys.argv) > 1 else None)
    try:
        args = parser.parse_args(argv)
        code, report = args.handler(args)
        _emit(report)
        return code
    except CommandError as exc:
        _emit(_error_report(command_name or "case_io", exc))
        return exc.exit_code
    except runtime.JsonDataError as exc:
        error = CommandError("invalid_json", str(exc), 2)
        _emit(_error_report(command_name or "case_io", error))
        return 2
    except (runtime.JsonPointerError, runtime.JsonPatchError) as exc:
        error = CommandError("invalid_change", str(exc), 2)
        _emit(_error_report(command_name or "case_io", error))
        return 2
    except OSError as exc:
        location = runtime.text(exc.filename or "", 300)
        message = exc.strerror or "file operation failed"
        if location:
            message += ": " + location
        error = CommandError("operational_error", message, 1)
        _emit(_error_report(command_name or "case_io", error))
        return 1
    except KeyboardInterrupt:
        error = CommandError("interrupted", "command interrupted", 1)
        _emit(_error_report(command_name or "case_io", error))
        return 1
    except Exception as exc:
        error = CommandError("operational_error", "unexpected %s during command" % type(exc).__name__, 1)
        _emit(_error_report(command_name or "case_io", error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
