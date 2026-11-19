"""Small, deterministic JSON and change-record primitives for the skill runtime."""

import copy
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone


class JsonDataError(ValueError):
    """Raised when a file or value is not strict, interoperable JSON."""


class JsonPointerError(ValueError):
    """Raised for an invalid RFC6901 pointer or lookup."""


class JsonPatchError(ValueError):
    """Raised when an RFC6902 operation cannot be applied."""


def text(value, limit=1000):
    """Return a single bounded string suitable for concise logs."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("text limit must be a non-negative integer")
    if isinstance(value, str):
        rendered = value
    else:
        try:
            rendered = json.dumps(
                value, ensure_ascii=False, sort_keys=True, default=repr,
                allow_nan=False,
            )
        except (TypeError, ValueError, RecursionError):
            rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    marker = "...[truncated]"
    if limit <= len(marker):
        return marker[:limit]
    return rendered[:limit - len(marker)] + marker


def _ensure_json_value(value, path="$", active=None):
    if active is None:
        active = set()
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise JsonDataError("non-finite number at " + path)
        return
    if type(value) not in (list, dict):
        raise JsonDataError(
            "unsupported JSON value type %s at %s" % (type(value).__name__, path)
        )
    identity = id(value)
    if identity in active:
        raise JsonDataError("cyclic JSON value at " + path)
    active.add(identity)
    try:
        if type(value) is list:
            for index, item in enumerate(value):
                _ensure_json_value(item, "%s/%d" % (path, index), active)
        else:
            for key, item in value.items():
                if type(key) is not str:
                    raise JsonDataError("non-string object key at " + path)
                _ensure_json_value(item, path + "/" + key, active)
    finally:
        active.remove(identity)


def _canonical_json(value):
    _ensure_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(value):
    """Hash canonical JSON without coercing values or reordering arrays."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _duplicate_checked_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key " + text(key, 120))
        result[key] = value
    return result


def _reject_constant(constant):
    raise ValueError("non-finite JSON number " + constant)


def read_json(path):
    """Read UTF-8 JSON, rejecting NaN, Infinity, and duplicate object keys."""
    source = os.fspath(path)
    try:
        with open(source, "r", encoding="utf-8") as handle:
            return json.load(
                handle,
                parse_constant=_reject_constant,
                object_pairs_hook=_duplicate_checked_object,
            )
    except json.JSONDecodeError as exc:
        raise JsonDataError(
            "invalid JSON in %s: %s at line %d column %d"
            % (text(source, 300), exc.msg, exc.lineno, exc.colno)
        ) from None
    except UnicodeDecodeError as exc:
        raise JsonDataError(
            "invalid UTF-8 in %s at byte %d" % (text(source, 300), exc.start)
        ) from None
    except RecursionError:
        raise JsonDataError("JSON nesting is too deep in " + text(source, 300)) from None
    except ValueError as exc:
        message = str(exc)
        if message.startswith("duplicate object key ") or message.startswith(
            "non-finite JSON number "
        ):
            raise JsonDataError(
                "invalid JSON in %s: %s" % (text(source, 300), message)
            ) from None
        raise


def write_json_atomic(path, data):
    """Write one complete strict JSON document and atomically replace the target."""
    destination = os.path.abspath(os.fspath(path))
    _ensure_json_value(data)
    try:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError, RecursionError) as exc:
        raise JsonDataError("value cannot be serialized as strict JSON: " + text(exc)) from None
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".result-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def sha256_file(path):
    """Return the SHA-256 of the exact bytes in a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return the current UTC time in RFC3339 form."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_pointer_tokens(pointer):
    """Decode an RFC6901 JSON pointer into unescaped reference tokens."""
    if not isinstance(pointer, str):
        raise JsonPointerError("JSON pointer must be a string")
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise JsonPointerError("JSON pointer must be empty or start with '/'")
    tokens = []
    for raw_token in pointer[1:].split("/"):
        token = []
        index = 0
        while index < len(raw_token):
            character = raw_token[index]
            if character != "~":
                token.append(character)
                index += 1
                continue
            if index + 1 >= len(raw_token) or raw_token[index + 1] not in "01":
                raise JsonPointerError("invalid '~' escape in JSON pointer")
            token.append("/" if raw_token[index + 1] == "1" else "~")
            index += 2
        tokens.append("".join(token))
    return tokens


def _lookup_tokens(document, tokens, pointer_for_error):
    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                raise JsonPointerError(
                    "object key not found at " + text(pointer_for_error, 240)
                )
            current = current[token]
        elif isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise JsonPointerError(
                    "invalid array index at " + text(pointer_for_error, 240)
                )
            index = int(token)
            if index >= len(current):
                raise JsonPointerError(
                    "array index out of bounds at " + text(pointer_for_error, 240)
                )
            current = current[index]
        else:
            raise JsonPointerError(
                "cannot traverse scalar at " + text(pointer_for_error, 240)
            )
    return current


def json_pointer_lookup(document, pointer):
    """Resolve an RFC6901 pointer; the empty pointer returns the root value."""
    return _lookup_tokens(document, json_pointer_tokens(pointer), pointer)


def _pointer_from_tokens(tokens):
    if not tokens:
        return ""
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)


def json_values_equal(left, right):
    """Compare JSON values using RFC6902 value equality, not Python bool equality."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            json_values_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            json_values_equal(left[key], right[key]) for key in left
        )
    return left == right


def _strict_json_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is float:
        if left != right:
            return False
        return left != 0 or math.copysign(1.0, left) == math.copysign(1.0, right)
    if type(left) is list:
        return len(left) == len(right) and all(
            _strict_json_equal(a, b) for a, b in zip(left, right)
        )
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _strict_json_equal(left[key], right[key]) for key in left
        )
    return left == right


def make_patch(before, after):
    """Create a deterministic, executable RFC6902 change list."""
    _ensure_json_value(before)
    _ensure_json_value(after)
    operations = []

    def difference(old, new, tokens):
        if _strict_json_equal(old, new):
            return
        pointer = _pointer_from_tokens(tokens)
        if type(old) is dict and type(new) is dict:
            for key in sorted(old.keys() - new.keys()):
                path = _pointer_from_tokens(tokens + [key])
                operations.append({"op": "test", "path": path, "value": copy.deepcopy(old[key])})
                operations.append({"op": "remove", "path": path})
            for key in sorted(old.keys() & new.keys()):
                difference(old[key], new[key], tokens + [key])
            for key in sorted(new.keys() - old.keys()):
                operations.append({
                    "op": "add",
                    "path": _pointer_from_tokens(tokens + [key]),
                    "value": copy.deepcopy(new[key]),
                })
            return
        operations.append({"op": "test", "path": pointer, "value": copy.deepcopy(old)})
        operations.append({"op": "replace", "path": pointer, "value": copy.deepcopy(new)})

    difference(before, after, [])
    return operations


def apply_patch(document, operations):
    """Apply RFC6902 test/add/replace/remove operations to an isolated deep copy."""
    _ensure_json_value(document)
    if type(operations) is not list:
        raise JsonPatchError("patch operations must be an array")
    result = copy.deepcopy(document)

    def parent_for(tokens, pointer):
        if not tokens:
            return None, None
        return _lookup_tokens(result, tokens[:-1], pointer), tokens[-1]

    for index, operation in enumerate(operations):
        if type(operation) is not dict:
            raise JsonPatchError("operation %d is not an object" % index)
        kind = operation.get("op")
        pointer = operation.get("path")
        if not isinstance(kind, str) or not isinstance(pointer, str):
            raise JsonPatchError("operation %d needs string op and path" % index)
        if kind not in ("test", "add", "replace", "remove"):
            raise JsonPatchError("operation %d uses unsupported op %s" % (index, kind))
        try:
            tokens = json_pointer_tokens(pointer)
            if kind in ("test", "replace", "add") and "value" not in operation:
                raise JsonPatchError("operation %d is missing value" % index)
            if "value" in operation:
                _ensure_json_value(operation["value"])
            if kind == "test":
                actual = _lookup_tokens(result, tokens, pointer)
                if not json_values_equal(actual, operation["value"]):
                    raise JsonPatchError("test failed at " + text(pointer, 240))
                continue
            if not tokens:
                if kind == "remove":
                    raise JsonPatchError("cannot remove the whole JSON document")
                result = copy.deepcopy(operation["value"])
                continue
            parent, key = parent_for(tokens, pointer)
            if isinstance(parent, dict):
                if kind in ("replace", "remove") and key not in parent:
                    raise JsonPatchError("target does not exist at " + text(pointer, 240))
                if kind == "remove":
                    del parent[key]
                else:
                    parent[key] = copy.deepcopy(operation["value"])
            elif isinstance(parent, list):
                if kind == "add" and key == "-":
                    parent.append(copy.deepcopy(operation["value"]))
                    continue
                if not re.fullmatch(r"0|[1-9][0-9]*", key):
                    raise JsonPatchError("invalid array index at " + text(pointer, 240))
                array_index = int(key)
                if kind == "add":
                    if array_index > len(parent):
                        raise JsonPatchError("array add index out of bounds at " + text(pointer, 240))
                    parent.insert(array_index, copy.deepcopy(operation["value"]))
                else:
                    if array_index >= len(parent):
                        raise JsonPatchError("array index out of bounds at " + text(pointer, 240))
                    if kind == "replace":
                        parent[array_index] = copy.deepcopy(operation["value"])
                    else:
                        del parent[array_index]
            else:
                raise JsonPatchError("cannot modify scalar parent at " + text(pointer, 240))
        except JsonPointerError as exc:
            raise JsonPatchError("operation %d: %s" % (index, str(exc))) from None
    _ensure_json_value(result)
    return result


def diff_documents(before, after):
    """Alias suitable for callers constructing change records."""
    return make_patch(before, after)


def verify_patch(before, after, operations):
    """Verify a complete patch without modifying either input document."""
    candidate = apply_patch(before, operations)
    if not json_values_equal(candidate, after) or not _strict_json_equal(candidate, after):
        raise JsonPatchError("applied patch does not equal the after document")
    return True
