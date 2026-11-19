#!/usr/bin/env python3
"""Exact, prospective resource-calendar audits; no booking or external lookup.

Numeric times are exact decimal minutes from an optional ISO ``time_origin``.
Without that origin they remain abstract offset minutes and cannot be mixed with
ISO times. ISO inputs must carry a timezone and are normalized to UTC internally.
All intervals are half-open. Generated schedules use deterministic input-order
topological serial placement, not a global optimization or feasibility search.
"""

import argparse
import heapq
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path


ALGORITHM = "input-order-topological-serial-earliest-placement-v1"
MAX_CANDIDATES_PER_TASK = 10000
TIME_LIMIT_SECONDS = 5.0
EPOCH = datetime(1970, 1, 1)
NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
ISO_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})[Tt ]"
    r"(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?"
    r"([Zz]|[+-]\d{2}:?\d{2})\Z"
)


class DataError(ValueError):
    def __init__(self, code, message, path):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


class LimitHit(RuntimeError):
    pass


@dataclass
class Task:
    task_id: str
    path: str
    index: int
    duration: object = None
    predecessors: list = field(default_factory=list)
    requirements: list = field(default_factory=list)
    release: object = None
    deadline: object = None
    start: object = None
    start_raw: object = None
    release_raw: object = None
    deadline_raw: object = None
    display_tz: object = None
    invalid: bool = False


@dataclass
class Calendar:
    resource_id: str
    path: str
    capacity: object = None
    windows: object = None
    availability_state: str = "known"
    display_tz: object = None
    invalid: bool = False


@dataclass
class Placement:
    start: Fraction
    end: Fraction
    provided: bool


def number(value, path, minimum=None, strictly_positive=False):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise DataError("invalid_number", "Expected an exact numeric string or integer.", path)
    text = str(value).strip()
    match = NUMBER_RE.fullmatch(text) if len(text) <= 1000 else None
    if not match:
        raise DataError("invalid_number", "Expected a finite decimal numeric value.", path)
    exponent = re.search(r"[eE]([+-]?\d+)$", text)
    if exponent and abs(int(exponent.group(1))) > 1000:
        raise DataError("numeric_out_of_range", "Decimal exponent exceeds the bounded audit range.", path)
    try:
        result = Fraction(text)
    except (ValueError, ArithmeticError) as exc:
        raise DataError("invalid_number", "Cannot parse the exact numeric value: %s" % exc, path)
    if strictly_positive and result <= 0:
        raise DataError("invalid_number", "Value must be greater than zero.", path)
    if minimum is not None and result < minimum:
        raise DataError("invalid_number", "Value must be at least %s." % minimum, path)
    return result


def identifier(value, path):
    if not isinstance(value, str) or not value.strip():
        raise DataError("invalid_id", "Expected a non-empty string identifier.", path)
    return value


def offset_text(offset):
    if offset == 0:
        return "Z"
    sign = "+" if offset >= 0 else "-"
    value = abs(offset)
    return "%s%02d:%02d" % (sign, value // 60, value % 60)


def parse_iso(value, path):
    if not isinstance(value, str):
        raise DataError("invalid_datetime", "Expected an ISO datetime with timezone.", path)
    match = ISO_RE.fullmatch(value.strip())
    if not match:
        raise DataError(
            "invalid_datetime",
            "Expected YYYY-MM-DDTHH:MM[:SS[.fraction]] followed by Z or a numeric timezone offset.",
            path,
        )
    date_text, hour, minute, second, fraction, zone = match.groups()
    second = second or "0"
    sign = -1 if zone.startswith("-") else 1
    if zone in ("Z", "z"):
        offset = 0
    else:
        digits = zone[1:].replace(":", "")
        hours, minutes = int(digits[:2]), int(digits[2:])
        if hours > 23 or minutes > 59:
            raise DataError("invalid_datetime", "Timezone offset is outside the supported ISO range.", path)
        offset = sign * (hours * 60 + minutes)
    try:
        local = datetime(
            int(date_text[:4]), int(date_text[5:7]), int(date_text[8:10]),
            int(hour), int(minute), int(second),
        )
    except ValueError as exc:
        raise DataError("invalid_datetime", "Invalid ISO datetime: %s" % exc, path)
    delta = local - EPOCH
    fractional_second = Fraction(0) if not fraction else Fraction(int(fraction), 10 ** len(fraction))
    utc_minutes = Fraction(delta.days * 86400 + delta.seconds, 60) + fractional_second / 60
    return utc_minutes - offset, offset


def fraction_text(value):
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    numerator, denominator = abs(value.numerator), value.denominator
    whole, remainder = divmod(numerator, denominator)
    twos = fives = 0
    rest = denominator
    while rest % 2 == 0:
        rest //= 2
        twos += 1
    while rest % 5 == 0:
        rest //= 5
        fives += 1
    if rest != 1:
        return "%s/%s" % (value.numerator, value.denominator)
    places = max(twos, fives)
    scaled = remainder * (2 ** (places - twos)) * (5 ** (places - fives))
    digits = str(scaled).rjust(places, "0").rstrip("0")
    return "%s%s.%s" % (sign, whole, digits)


def iso_text(minutes, offset=0):
    seconds = minutes * 60
    whole = seconds.numerator // seconds.denominator
    remainder = seconds - whole
    try:
        local = EPOCH + timedelta(seconds=whole + offset * 60)
    except (OverflowError, ValueError) as exc:
        raise DataError("datetime_out_of_range", "Datetime cannot be represented exactly: %s" % exc, "schedule")
    digits = fraction_text(remainder)
    if "/" in digits:
        raise DataError("datetime_precision_unsupported", "ISO seconds would require a repeating decimal.", "schedule")
    fraction = digits.partition(".")[2]
    base = "%04d-%02d-%02dT%02d:%02d:%02d" % (
        local.year, local.month, local.day, local.hour, local.minute, local.second,
    )
    return base + (("." + fraction) if fraction else "") + offset_text(offset)


def contains(windows, start, end):
    if start == end:
        return any(left <= start < right for left, right in windows)
    return any(left <= start and end <= right for left, right in windows)


def capacity_fits(start, end, units, capacity, busy):
    if start == end:
        return True
    points = {start, end}
    for left, right, _, _ in busy:
        if left < end and right > start:
            points.add(max(start, left))
            points.add(min(end, right))
    ordered = sorted(points)
    for left, right in zip(ordered, ordered[1:]):
        used = units + sum(
            amount for busy_left, busy_right, amount, _ in busy
            if busy_left <= left and busy_right >= right
        )
        if used > capacity:
            return False
    return True


class Audit:
    def __init__(self, candidate):
        self.candidate = candidate if isinstance(candidate, dict) else {}
        self.candidate_id = self.candidate.get("candidate_id")
        self.parent_id = self.candidate.get("parent_id")
        self.origin = Fraction(0)
        self.origin_raw = None
        self.origin_tz = None
        self.has_numeric = False
        self.has_iso = False
        self.incompatible_time_bases = False
        self.tasks = []
        self.task_by_id = {}
        self.calendars = {}
        self.placements = {}
        self.violations = []
        self.unmet_calendars = []
        self.generated = False
        self.limit_hit = False
        self.recheck_performed = False
        self.global_tz = None
        self.stop_at = time.monotonic() + TIME_LIMIT_SECONDS
        self._violation_keys = set()

    def tick(self):
        if time.monotonic() > self.stop_at:
            self.limit_hit = True
            raise LimitHit("The scheduling audit reached its time limit.")

    def add_violation(self, severity, code, message, path, task_id=None, resource_id=None, **details):
        key = (severity, code, path, task_id, resource_id, repr(sorted(details.items())))
        if key in self._violation_keys:
            return
        self._violation_keys.add(key)
        item = {"severity": severity, "code": code, "message": message, "path": path}
        if task_id is not None:
            item["task_id"] = task_id
        if resource_id is not None:
            item["resource_id"] = resource_id
        item.update(details)
        self.violations.append(item)

    def fail(self, code, message, path, task_id=None, resource_id=None, **details):
        self.add_violation("fail", code, message, path, task_id, resource_id, **details)

    def unknown(self, code, message, path, task_id=None, resource_id=None, **details):
        self.add_violation("unknown", code, message, path, task_id, resource_id, **details)

    def parse_time(self, value, path):
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise DataError("invalid_time", "Expected offset minutes or an ISO datetime with timezone.", path)
        text = str(value).strip()
        if NUMBER_RE.fullmatch(text):
            self.has_numeric = True
            if not self.origin_raw and self.has_iso:
                self.incompatible_time_bases = True
                raise DataError("mixed_time_bases", "Cannot mix offset minutes and ISO times without time_origin.", path)
            return self.origin + number(value, path), None
        self.has_iso = True
        if not self.origin_raw and self.has_numeric:
            self.incompatible_time_bases = True
            raise DataError("mixed_time_bases", "Cannot mix offset minutes and ISO times without time_origin.", path)
        parsed, zone = parse_iso(text, path)
        if self.global_tz is None:
            self.global_tz = zone
        return parsed, zone

    def parse_task(self, raw, index):
        path = "tasks[%d]" % index
        if not isinstance(raw, dict):
            raise DataError("invalid_task", "Each task must be an object.", path)
        before = len(self.violations)
        task = Task(identifier(raw.get("id"), path + ".id"), path, index)
        if task.task_id in self.task_by_id:
            raise DataError("duplicate_task_id", "Task IDs must be unique.", path + ".id")
        if "duration_minutes" not in raw:
            self.unknown(
                "missing_duration", "Duration is unknown; zero is not assumed.",
                path + ".duration_minutes", task.task_id,
            )
        else:
            task.duration = number(raw["duration_minutes"], path + ".duration_minutes", minimum=0)
        predecessors = raw.get("predecessors", [])
        if not isinstance(predecessors, list):
            raise DataError("invalid_predecessors", "predecessors must be a list of task IDs.", path + ".predecessors")
        for position, predecessor in enumerate(predecessors):
            predecessor = identifier(predecessor, "%s.predecessors[%d]" % (path, position))
            if predecessor in task.predecessors:
                raise DataError("duplicate_predecessor", "Duplicate predecessor reference.", "%s.predecessors[%d]" % (path, position))
            if predecessor == task.task_id:
                raise DataError("dependency_cycle", "A task cannot precede itself.", "%s.predecessors[%d]" % (path, position))
            task.predecessors.append(predecessor)
        resources = raw.get("resources", [])
        if not isinstance(resources, list):
            raise DataError("invalid_resources", "resources must be a list.", path + ".resources")
        seen_resources = set()
        for position, requirement in enumerate(resources):
            requirement_path = "%s.resources[%d]" % (path, position)
            if not isinstance(requirement, dict):
                raise DataError("invalid_resource_requirement", "Each resource requirement must be an object.", requirement_path)
            resource_id = identifier(requirement.get("resource_id"), requirement_path + ".resource_id")
            if resource_id in seen_resources:
                raise DataError("duplicate_resource_requirement", "Duplicate resource requirement for task.", requirement_path + ".resource_id")
            seen_resources.add(resource_id)
            units = number(requirement.get("units"), requirement_path + ".units", strictly_positive=True)
            task.requirements.append((resource_id, units, requirement_path))
        if "earliest_start" in raw:
            task.release_raw = raw["earliest_start"]
            task.release, zone = self.parse_time(raw["earliest_start"], path + ".earliest_start")
            if zone is not None:
                task.display_tz = zone
        if "deadline" in raw:
            task.deadline_raw = raw["deadline"]
            task.deadline, zone = self.parse_time(raw["deadline"], path + ".deadline")
            if zone is not None:
                task.display_tz = zone
        else:
            self.unknown(
                "missing_deadline", "Deadline is unknown; an earliest proposal is not a global readiness claim.",
                path + ".deadline", task.task_id,
            )
        if "start" in raw:
            task.start_raw = raw["start"]
            task.start, zone = self.parse_time(raw["start"], path + ".start")
            if zone is not None:
                task.display_tz = zone
        if raw.get("interruptible", False) is True:
            raise DataError("unsupported_task_mode", "Interruptible/preemptive tasks are not supported.", path + ".interruptible")
        if "interruptible" in raw and not isinstance(raw["interruptible"], bool):
            raise DataError("invalid_task_mode", "interruptible must be boolean when supplied.", path + ".interruptible")
        mode = raw.get("mode")
        if isinstance(mode, str) and mode.strip().lower() in ("interruptible", "preemptive", "pre-emptive"):
            raise DataError("unsupported_task_mode", "Interruptible/preemptive tasks are not supported.", path + ".mode")
        task.invalid = len(self.violations) > before and any(
            item["severity"] == "fail" for item in self.violations[before:]
        )
        return task

    def parse_calendar(self, raw, index):
        path = "resource_calendars[%d]" % index
        if not isinstance(raw, dict):
            raise DataError("invalid_calendar", "Each resource calendar must be an object.", path)
        resource_id = identifier(raw.get("resource_id"), path + ".resource_id")
        if resource_id in self.calendars:
            raise DataError("duplicate_resource_id", "Resource calendar IDs must be unique.", path + ".resource_id")
        calendar = Calendar(resource_id, path)
        if "capacity" not in raw:
            calendar.capacity = None
        else:
            calendar.capacity = number(raw["capacity"], path + ".capacity", minimum=0)
        if "available_intervals" not in raw or raw["available_intervals"] is None:
            calendar.availability_state = "missing"
            calendar.windows = None
        else:
            intervals = raw["available_intervals"]
            if not isinstance(intervals, list):
                raise DataError("invalid_availability", "available_intervals must be a list of [start,end] pairs.", path + ".available_intervals")
            windows = []
            for position, interval in enumerate(intervals):
                interval_path = "%s.available_intervals[%d]" % (path, position)
                if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                    raise DataError("invalid_availability", "Each available interval must contain exactly two endpoints.", interval_path)
                start, start_zone = self.parse_time(interval[0], interval_path + "[0]")
                end, _ = self.parse_time(interval[1], interval_path + "[1]")
                if start_zone is not None and calendar.display_tz is None:
                    calendar.display_tz = start_zone
                if end < start:
                    raise DataError("invalid_availability", "Availability end precedes its start.", interval_path)
                if start != end:
                    windows.append((start, end))
            windows.sort()
            merged = []
            for start, end in windows:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            calendar.windows = merged
            if not merged:
                calendar.availability_state = "empty"
        return calendar

    def topology(self):
        for task in self.tasks:
            for position, predecessor in enumerate(task.predecessors):
                if predecessor not in self.task_by_id:
                    task.invalid = True
                    self.fail(
                        "unknown_predecessor", "Predecessor task ID does not exist.",
                        "%s.predecessors[%d]" % (task.path, position), task.task_id,
                        predecessor_id=predecessor,
                    )
        indegree = {task.task_id: 0 for task in self.tasks if not task.invalid}
        successors = {task_id: [] for task_id in indegree}
        for task in self.tasks:
            if task.invalid:
                continue
            for predecessor in task.predecessors:
                if predecessor in indegree:
                    indegree[task.task_id] += 1
                    successors[predecessor].append(task.task_id)
        ready = [(self.task_by_id[task_id].index, task_id) for task_id, degree in indegree.items() if degree == 0]
        heapq.heapify(ready)
        ordered = []
        while ready:
            self.tick()
            _, task_id = heapq.heappop(ready)
            ordered.append(task_id)
            for successor in successors[task_id]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    heapq.heappush(ready, (self.task_by_id[successor].index, successor))
        cyclic = sorted(set(indegree) - set(ordered), key=lambda item: self.task_by_id[item].index)
        if cyclic:
            for task_id in cyclic:
                self.task_by_id[task_id].invalid = True
            self.fail(
                "dependency_cycle", "The dependency graph contains a cycle.",
                "tasks", task_ids=cyclic,
            )
        return ordered

    def report_unmet_calendars(self):
        active = []
        for task in self.tasks:
            for resource_id, _, _ in task.requirements:
                if resource_id not in active:
                    active.append(resource_id)
        for resource_id in active:
            calendar = self.calendars.get(resource_id)
            if calendar is None:
                path = "resource_calendars"
                reasons = ["calendar_missing"]
                task_id = None
            else:
                path = calendar.path
                reasons = []
                task_id = None
                if calendar.capacity is None:
                    reasons.append("capacity_missing")
                if calendar.availability_state in ("missing", "empty"):
                    reasons.append("available_intervals_" + calendar.availability_state)
            if not reasons:
                continue
            self.unmet_calendars.append({"resource_id": resource_id, "path": path, "reasons": reasons})
            self.unknown(
                "unknown_resource_calendar",
                "Resource capacity or availability is unknown; it is not treated as zero or unlimited.",
                path, task_id, resource_id, reasons=reasons,
            )

    def known_calendar(self, resource_id):
        calendar = self.calendars.get(resource_id)
        return (
            calendar is not None and not calendar.invalid and calendar.capacity is not None
            and calendar.windows is not None and bool(calendar.windows)
        )

    def busy(self, task, placements):
        required = {resource_id for resource_id, _, _ in task.requirements}
        result = {resource_id: [] for resource_id in required}
        for other_id, placement in placements.items():
            other = self.task_by_id.get(other_id)
            if other is None or placement.start == placement.end:
                continue
            for resource_id, units, _ in other.requirements:
                if resource_id in required:
                    result[resource_id].append((placement.start, placement.end, units, other_id))
        for intervals in result.values():
            intervals.sort(key=lambda item: (item[0], item[1], item[3]))
        return result

    def search(self, task, release, placements, counter):
        lower = release
        if lower is None:
            if not task.requirements:
                return None, "unbounded"
            lower = max(self.calendars[resource_id].windows[0][0] for resource_id, _, _ in task.requirements)
        candidates = {lower}
        busy = self.busy(task, placements)
        for resource_id, _, _ in task.requirements:
            for left, _ in self.calendars[resource_id].windows:
                if left >= lower:
                    candidates.add(left)
            for _, right, _, _ in busy[resource_id]:
                if right >= lower:
                    candidates.add(right)
        for start in sorted(candidates):
            self.tick()
            counter[0] += 1
            if counter[0] > MAX_CANDIDATES_PER_TASK:
                self.limit_hit = True
                raise LimitHit("The candidate-point iteration limit was reached.")
            end = start + task.duration
            if task.deadline is not None and end > task.deadline:
                break
            possible = True
            for resource_id, units, _ in task.requirements:
                calendar = self.calendars[resource_id]
                if units > calendar.capacity or not contains(calendar.windows, start, end):
                    possible = False
                    break
                if not capacity_fits(start, end, units, calendar.capacity, busy[resource_id]):
                    possible = False
                    break
            if possible:
                return Placement(start, end, False), "placed"
        return None, "exhausted"

    def place(self, task, release):
        counter = [0]
        placement, state = self.search(task, release, self.placements, counter)
        if state == "placed":
            return placement
        if state == "unbounded":
            self.unknown(
                "unbounded_release", "No predecessor, release, or calendar supplies a finite earliest candidate point.",
                task.path, task.task_id,
            )
            return None
        empty, empty_state = self.search(task, release, {}, counter)
        if empty_state == "exhausted":
            self.fail(
                "no_feasible_window",
                "No joint nonpreemptive calendar window satisfies release, duration, and deadline, even before occupancy.",
                task.path, task.task_id,
            )
            return None
        if empty_state == "unbounded":
            self.unknown("unbounded_release", "The earliest placement is unbounded below.", task.path, task.task_id)
            return None
        fixed = {key: value for key, value in self.placements.items() if value.provided}
        _, fixed_state = self.search(task, release, fixed, counter)
        if fixed_state == "exhausted":
            self.fail(
                "fixed_resource_conflict",
                "No legal placement remains with the supplied fixed starts and calendar/deadline constraints.",
                task.path, task.task_id,
            )
        else:
            self.unknown(
                "serial_search_incomplete",
                "The input-order serial placement found no slot, but another non-serial ordering was not proved infeasible.",
                task.path, task.task_id,
            )
        return None

    def generate(self, ordered):
        for task in self.tasks:
            if not task.invalid and task.duration is not None and task.start is not None:
                self.placements[task.task_id] = Placement(task.start, task.start + task.duration, True)
        for task_id in ordered:
            self.tick()
            task = self.task_by_id[task_id]
            if task.invalid or task_id in self.placements:
                continue
            if task.duration is None:
                continue
            release = task.release
            blocked = False
            for predecessor in task.predecessors:
                placement = self.placements.get(predecessor)
                if placement is None:
                    blocked = True
                    break
                release = placement.end if release is None else max(release, placement.end)
            if blocked:
                self.unknown(
                    "predecessor_unscheduled", "A predecessor has no verified end, so this task cannot be placed.",
                    task.path, task.task_id,
                )
                continue
            if any(not self.known_calendar(resource_id) for resource_id, _, _ in task.requirements):
                continue
            placement = self.place(task, release)
            if placement is not None:
                self.placements[task_id] = placement
                self.generated = True

    def point_fields(self, target, name, value, zone):
        primary_iso = self.has_iso and not self.has_numeric
        relative = value - self.origin
        target[name + "_minutes"] = fraction_text(relative)
        utc_meaningful = self.origin_raw is not None or primary_iso
        if primary_iso:
            target[name] = iso_text(value, 0)
            target[name + "_utc"] = target[name]
            target[name + "_time_origin"] = "1970-01-01T00:00:00Z"
        else:
            target[name] = fraction_text(relative)
            if self.origin_raw is not None:
                target[name + "_time_origin"] = self.origin_raw
        if utc_meaningful:
            try:
                target[name + "_utc"] = iso_text(value, 0)
                if zone is not None:
                    target[name + "_at_source_timezone"] = iso_text(value, zone)
            except DataError:
                target[name + "_utc"] = None
                if primary_iso:
                    target[name] = target[name + "_minutes"]
                    target["unit"] = "minutes_from_1970-01-01T00:00:00Z"
                    return False
        if zone is not None:
            target[name + "_source_timezone"] = offset_text(zone)
        return True

    def independent_recheck(self):
        for task in self.tasks:
            placement = self.placements.get(task.task_id)
            if placement is None:
                if not task.invalid and task.duration is None:
                    continue
                if not task.invalid:
                    self.unknown("task_unscheduled", "No complete start/end placement was established.", task.path, task.task_id)
                continue
            start, end = placement.start, placement.end
            for predecessor in task.predecessors:
                predecessor_placement = self.placements.get(predecessor)
                if predecessor_placement is None:
                    self.unknown(
                        "dependency_unverified", "Predecessor has no complete placement.",
                        task.path + ".start", task.task_id, predecessor_id=predecessor,
                    )
                elif start < predecessor_placement.end:
                    self.fail(
                        "predecessor_violation", "Task starts before its predecessor ends.",
                        task.path + ".start", task.task_id, predecessor_id=predecessor,
                        predecessor_end=fraction_text(predecessor_placement.end - self.origin),
                    )
            if task.release is not None and start < task.release:
                self.fail("release_violation", "Task starts before earliest_start.", task.path + ".start", task.task_id)
            if task.deadline is not None and end > task.deadline:
                self.fail("deadline_violation", "Task ends after its deadline.", task.path + ".deadline", task.task_id)
            for resource_id, units, requirement_path in task.requirements:
                calendar = self.calendars.get(resource_id)
                if calendar is None or calendar.invalid:
                    continue
                if calendar.capacity is not None and units > calendar.capacity:
                    self.fail(
                        "resource_capacity_exceeded", "Required units exceed declared resource capacity.",
                        requirement_path + ".units", task.task_id, resource_id,
                        required_units=fraction_text(units), capacity=fraction_text(calendar.capacity),
                    )
                if calendar.windows and not contains(calendar.windows, start, end):
                    self.fail(
                        "availability_violation", "The complete task is not contained in one joint availability window.",
                        requirement_path, task.task_id, resource_id,
                    )
        for resource_id, calendar in self.calendars.items():
            self.tick()
            if calendar.capacity is None:
                continue
            intervals = []
            for task in self.tasks:
                placement = self.placements.get(task.task_id)
                if placement is None or placement.start == placement.end:
                    continue
                for required_id, units, _ in task.requirements:
                    if required_id == resource_id:
                        intervals.append((placement.start, placement.end, units, task.task_id))
            points = sorted({point for left, right, _, _ in intervals for point in (left, right)})
            for left, right in zip(points, points[1:]):
                self.tick()
                active = [item for item in intervals if item[0] <= left and item[1] >= right]
                used = sum((item[2] for item in active), Fraction(0))
                if used > calendar.capacity:
                    self.fail(
                        "resource_overlap", "Resource usage exceeds capacity on this timeline segment.",
                        "schedule", resource_id=resource_id,
                        task_ids=[item[3] for item in active],
                        segment_start=fraction_text(left - self.origin),
                        segment_end=fraction_text(right - self.origin),
                        used_units=fraction_text(used), capacity=fraction_text(calendar.capacity),
                    )

    def run(self):
        for key in ("candidate_id", "parent_id"):
            if self.candidate.get(key) is not None:
                identifier(self.candidate[key], key)
        if "time_origin" in self.candidate and self.candidate["time_origin"] is not None:
            self.origin_raw = self.candidate["time_origin"]
            self.origin, self.origin_tz = parse_iso(self.origin_raw, "time_origin")
            if self.global_tz is None:
                self.global_tz = self.origin_tz
        horizon_raw = self.candidate.get("horizon_minutes")
        global_deadline = None
        if horizon_raw is not None:
            global_deadline = number(horizon_raw, "horizon_minutes", minimum=0)
        raw_tasks = self.candidate.get("tasks")
        if not isinstance(raw_tasks, list):
            raise DataError("invalid_tasks", "tasks must be supplied as a list.", "tasks")
        for index, raw in enumerate(raw_tasks):
            self.tick()
            try:
                task = self.parse_task(raw, index)
                if task.deadline is None and global_deadline is not None:
                    task.deadline = self.origin + global_deadline
                    self.violations = [
                        missing for missing in self.violations
                        if not (missing["code"] == "missing_deadline" and missing["task_id"] == task.task_id)
                    ]
                    self.add_violation(
                        "info", "global_deadline_applied",
                        "The candidate-wide horizon applies to this task; this does not invent a task-specific deadline.",
                        task.path + ".deadline", task.task_id,
                        provenance="candidate.horizon_minutes",
                    )
            except DataError as exc:
                task_id = raw.get("id") if isinstance(raw, dict) and isinstance(raw.get("id"), str) else None
                self.fail(exc.code, exc.message, exc.path, task_id)
                continue
            self.tasks.append(task)
            self.task_by_id[task.task_id] = task
        raw_calendars = self.candidate.get("resource_calendars", [])
        if not isinstance(raw_calendars, list):
            raise DataError("invalid_calendars", "resource_calendars must be a list.", "resource_calendars")
        for index, raw in enumerate(raw_calendars):
            self.tick()
            try:
                calendar = self.parse_calendar(raw, index)
            except DataError as exc:
                resource_id = raw.get("resource_id") if isinstance(raw, dict) and isinstance(raw.get("resource_id"), str) else None
                self.fail(exc.code, exc.message, exc.path, resource_id=resource_id)
                continue
            self.calendars[calendar.resource_id] = calendar
        ordered = self.topology()
        self.report_unmet_calendars()
        for task in self.tasks:
            for resource_id, units, requirement_path in task.requirements:
                calendar = self.calendars.get(resource_id)
                if calendar is not None and calendar.capacity is not None and units > calendar.capacity:
                    self.fail(
                        "resource_capacity_exceeded", "Required units exceed declared resource capacity.",
                        requirement_path + ".units", task.task_id, resource_id,
                        required_units=fraction_text(units), capacity=fraction_text(calendar.capacity),
                    )
        self.generate(ordered)
        self.independent_recheck()
        self.recheck_performed = True

    def status_is(self, severity):
        return any(item["severity"] == severity for item in self.violations)

    def limitations(self):
        items = [
            "Prospective scenario audit only: no appointment is booked and external availability is not confirmed.",
            "Input-order topological serial placement is deterministic and nonpreemptive; it is not a global optimum or global feasibility proof.",
            "Missing or explicitly empty availability is unknown, never unlimited; no shifts, timezones, capacities, or durations are inferred.",
            "Missing task-specific deadlines are not inferred; an explicitly declared candidate-wide horizon applies to each included task with its original scope.",
            "Unbounded roots and iteration/time-limit exhaustion return unknown rather than proof of infeasibility.",
        ]
        if any(task.deadline is None for task in self.tasks):
            items.append("At least one task has no deadline; its proposed completion is not a guarantee of timely readiness.")
        return items

    def finish(self):
        schedule = []
        format_failed = False
        for task in self.tasks:
            placement = self.placements.get(task.task_id)
            zone = task.display_tz
            if zone is None:
                zone = self.origin_tz if self.origin_tz is not None else self.global_tz
            item = {
                "task_id": task.task_id,
                "path": task.path,
                "scheduled": placement is not None,
                "placement": ("provided" if placement.provided else "generated") if placement else "unscheduled",
                "unit": "ISO8601_UTC" if self.has_iso and not self.has_numeric else "minutes",
                "duration_minutes": fraction_text(task.duration) if task.duration is not None else None,
                "provided_start": task.start_raw,
                "earliest_start": task.release_raw,
                "deadline": task.deadline_raw,
                "prospective_not_booked": True,
            }
            if placement is not None:
                try:
                    if not self.point_fields(item, "start", placement.start, zone):
                        format_failed = True
                    if not self.point_fields(item, "end", placement.end, zone):
                        format_failed = True
                except DataError as exc:
                    item["start"] = item["end"] = None
                    item["scheduled"] = False
                    format_failed = True
                    self.unknown(exc.code, exc.message, task.path, task.task_id)
            else:
                item["start"] = item["end"] = None
            item["resources"] = [
                {
                    "resource_id": resource_id,
                    "units": fraction_text(units),
                    "requirement_path": requirement_path,
                    "calendar_path": self.calendars[resource_id].path if resource_id in self.calendars else None,
                }
                for resource_id, units, requirement_path in task.requirements
            ]
            schedule.append(item)
        if format_failed:
            self.unknown("time_format_incomplete", "Some UTC display fields are unavailable; exact minute values remain authoritative.", "schedule")
        coverage = len(self.placements) == len(self.tasks) and not self.incompatible_time_bases
        makespan = None
        if coverage and self.tasks:
            start = min(item.start for item in self.placements.values())
            end = max(item.end for item in self.placements.values())
            makespan = {"duration_minutes": fraction_text(end - start), "unit": "ISO8601_UTC" if self.has_iso and not self.has_numeric else "minutes"}
            try:
                self.point_fields(makespan, "start", start, self.global_tz)
                self.point_fields(makespan, "end", end, self.global_tz)
            except DataError:
                makespan = None
        elif coverage and not self.tasks:
            makespan = {"duration_minutes": "0", "unit": "minutes"}
        has_fail = self.status_is("fail")
        has_unknown = self.status_is("unknown") or not coverage or self.limit_hit
        status = "fail" if has_fail else ("unknown" if has_unknown else "pass")
        categories = {
            "dependencies": ("predecessor_violation", "dependency_cycle", "unknown_predecessor", "dependency_unverified", "predecessor_unscheduled"),
            "deadlines": ("deadline_violation", "missing_deadline"),
            "calendars": ("availability_violation", "no_feasible_window", "unknown_resource_calendar"),
            "capacity": ("resource_overlap", "resource_capacity_exceeded", "fixed_resource_conflict"),
        }
        checks = {}
        for name, codes in categories.items():
            matching = [item for item in self.violations if item["code"] in codes]
            checks[name] = "fail" if any(item["severity"] == "fail" for item in matching) else ("unknown" if matching else "pass")
        checks["complete"] = not has_unknown
        checks["independent_recheck_performed"] = self.recheck_performed
        return {
            "schema_version": "1.0",
            "candidate_id": self.candidate_id,
            "parent_id": self.parent_id,
            "status": status,
            "algorithm": ALGORITHM,
            "prospective_not_booked": True,
            "search_complete": not self.generated and not self.limit_hit,
            "global_optimum_claimed": False,
            "time_basis": {
                "arithmetic": "exact_fraction_minutes",
                "intervals": "half_open_[start,end)",
                "time_origin": self.origin_raw,
                "time_origin_utc": iso_text(self.origin, 0) if self.origin_raw is not None else None,
                "numeric_output_origin": "1970-01-01T00:00:00Z" if self.has_iso and not self.has_numeric else self.origin_raw,
                "iso_normalization": "UTC",
                "source_timezones_preserved": True,
            },
            "schedule": schedule,
            "makespan": makespan,
            "checks": checks,
            "violations": self.violations,
            "unmet_calendars": self.unmet_calendars,
            "limitations": self.limitations(),
        }


def audit_schedule(candidate):
    """Return a structured prospective schedule audit without raising on bad data."""
    audit = Audit(candidate)
    if not isinstance(candidate, dict):
        audit.fail("invalid_candidate", "Candidate must be an object.", "candidate")
        return audit.finish()
    try:
        audit.run()
    except DataError as exc:
        audit.fail(exc.code, exc.message, exc.path)
    except LimitHit as exc:
        audit.limit_hit = True
        audit.unknown("search_limit", str(exc) + " This is not proof of infeasibility.", "candidate")
    return audit.finish()


def select_candidate(document, candidate_id=None):
    if isinstance(document, dict) and "candidates" not in document:
        return document
    if not isinstance(document, dict) or not isinstance(document.get("candidates"), list):
        raise DataError("invalid_candidate_file", "Expected one candidate object or an audit object with a candidates list.", "candidate")
    candidates = document["candidates"]
    if not candidates:
        raise DataError("invalid_candidate_file", "The candidates list is empty.", "candidates")
    selected = None
    if candidate_id is None:
        selected = candidates[0]
    else:
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id:
                selected = candidate
                break
        if selected is None:
            raise DataError("candidate_not_found", "No candidate has the requested candidate_id.", "candidates")
    if not isinstance(selected, dict):
        raise DataError("invalid_candidate_file", "The selected candidate is not an object.", "candidates")
    if "time_origin" not in selected and "time_origin" in document:
        selected = dict(selected)
        selected["time_origin"] = document["time_origin"]
    return selected


def write_json_atomic(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, str(destination))
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit a prospective exact resource-calendar schedule.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "check"):
        subparser = subparsers.add_parser(command, help="Audit one candidate; check is an alias.")
        subparser.add_argument("--candidate", required=True, help="Candidate JSON or full audit JSON with candidates.")
        subparser.add_argument("--candidate-id", help="Select a candidate from a full audit; defaults to the first.")
        subparser.add_argument("--output", required=True, help="Report JSON path.")
    arguments = parser.parse_args(argv)
    try:
        with open(arguments.candidate, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        candidate = select_candidate(document, arguments.candidate_id)
        report = audit_schedule(candidate)
        write_json_atomic(arguments.output, report)
    except (OSError, json.JSONDecodeError, DataError) as exc:
        parser.exit(2, "schedule.py: error: %s\n" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
