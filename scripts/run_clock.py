#!/usr/bin/env python3
"""Advisory elapsed-time checkpoints, not model-request or hard deadline proof."""

import argparse
import json
import sys
import time
from pathlib import Path

import runtime


def report(path, reference_seconds):
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "run-clock.json"
    with path.open("r", encoding="utf-8") as handle:
        clock = json.load(handle)
    if clock.get("schema_version") != "weekly-skill.run-clock/v1":
        raise ValueError("Unsupported run-clock schema.")
    started = clock.get("started_at_epoch_seconds")
    reference = clock.get("reference_seconds")
    if (isinstance(started, bool) or not isinstance(started, (int, float))
            or isinstance(reference, bool) or not isinstance(reference, (int, float))
            or reference <= 0 or reference != reference_seconds):
        raise ValueError("Invalid start time or reference budget matching.")
    elapsed = max(0.0, time.time() - started)
    remaining = reference - elapsed
    action = "trusted_finalization_only" if elapsed >= reference else (
        "finish_material_analysis_and_validate" if elapsed >= 600 else "continue_source_bound_analysis"
    )
    return {
        "schema_version": "weekly-skill.run-check/v1",
        "elapsed_since_first_clock_seconds": round(elapsed, 3),
        "remaining_to_reference_seconds": round(remaining, 3),
        "reference_seconds": reference,
        "action": action,
        "hard_deadline_enforced": False,
        "scope": "Elapsed time since the first run_clock start, not total platform time or model usage. Callers must finish and validate truthful output; this helper cannot interrupt a long turn.",
    }


def start(work, reference_seconds):
    root = Path(work).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "run-clock.json"
    created = not path.exists()
    if created:
        runtime.write_json_atomic(str(path), {
            "schema_version": "weekly-skill.run-clock/v1",
            "started_at_epoch_seconds": time.time(),
            "reference_seconds": reference_seconds,
            "scope": "First tool checkpoint after loading; no earlier model time is inferred.",
        })
    result = report(path, reference_seconds)
    result["command"] = "start"
    result["clock_created"] = created
    result["clock_path"] = str(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "check"):
        sub = commands.add_parser(command)
        sub.add_argument("--work", required=True, help="Existing run work directory")
        sub.add_argument("--reference-seconds", type=int, default=900)
    arguments = parser.parse_args(argv)
    if arguments.reference_seconds <= 0:
        parser.error("--reference-seconds must be positive")
    try:
        if arguments.command == "start":
            result = start(arguments.work, arguments.reference_seconds)
        else:
            result = report(arguments.work, arguments.reference_seconds)
            result["command"] = "check"
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {"command": arguments.command, "status": "not_run", "error": str(error)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
