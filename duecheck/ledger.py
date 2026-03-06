"""Assignment ledger: persistent state tracking across sync runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import (
    LEDGER_SEVERITY_LABEL,
    LEDGER_STATUS_PRIORITY,
    AssignmentObservation,
    CourseInfo,
    LedgerEntry,
    format_due_at,
    format_due_date,
    ledger_entry_from_mapping,
    match_entry,
    parse_datetime,
    serialize_payload,
)


def load_existing_ledger(manifest_path: Path) -> dict[str, dict]:
    """Load a previous ledger from a JSON manifest file."""
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(errors="ignore"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}

    existing: dict[str, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        entry = ledger_entry_from_mapping(item)
        if not entry.name or not entry.course:
            continue
        current = serialize_payload(entry)
        previous = existing.get(entry.item_id)
        if previous is None or str(current["last_seen"]) >= str(previous.get("last_seen", "")):
            existing[entry.item_id] = current
    return existing


def merge_current_observation(
    observed: dict[str, dict],
    *,
    course: str,
    name: str,
    due_dt: datetime | None,
    status: str,
    source_key: str | None = None,
    course_info: CourseInfo | None = None,
    source_adapter: str = "canvas",
) -> None:
    """Merge a single observation into the current observed set."""
    entry = ledger_entry_from_mapping(
        {
            "source_key": source_key or "",
            "name": name,
            "course": course,
            "status": status,
            "due_at": format_due_at(due_dt),
            "date": format_due_date(due_dt),
            "severity_label": LEDGER_SEVERITY_LABEL[status],
            "course_score": course_info.score if course_info is not None else None,
            "course_grade": course_info.grade if course_info is not None and course_info.grade else "",
            "source_adapter": source_adapter,
        },
        default_source_adapter=source_adapter,
    )
    candidate = serialize_payload(entry)
    item_id = str(candidate["item_id"])
    candidate = {
        **candidate,
        "item_id": item_id,
    }
    matched_id, current = match_entry(
        observed,
        course=course,
        name=name,
        source_key=source_key,
        item_id=item_id,
    )
    if current is None:
        observed[item_id] = candidate
        return
    if matched_id and matched_id != item_id:
        observed.pop(matched_id, None)
        current = current.copy()
        current["item_id"] = item_id
        observed[item_id] = current
    if source_key and not current.get("source_key"):
        current["source_key"] = source_key
    if course_info is not None:
        current["course_score"] = course_info.score
        current["course_grade"] = course_info.grade or ""
    if LEDGER_STATUS_PRIORITY[status] > LEDGER_STATUS_PRIORITY[current["status"]]:
        observed[item_id] = candidate
        return
    if not current.get("due_at") and candidate["due_at"]:
        current["due_at"] = candidate["due_at"]
        current["date"] = candidate["date"]


def _entry_value(item: LedgerEntry | dict[str, Any], key: str) -> Any:
    if isinstance(item, LedgerEntry):
        return getattr(item, key, "")
    return item.get(key)


def sort_ledger(ledger: list[LedgerEntry | dict[str, Any]]) -> list[LedgerEntry | dict[str, Any]]:
    """Sort ledger entries: active first by due date, then inactive."""
    return sorted(
        ledger,
        key=lambda item: (
            1 if _entry_value(item, "status") == "not_observed" else 0,
            _entry_value(item, "due_at") or _entry_value(item, "date") or "9999-12-31T23:59:59Z",
            str(_entry_value(item, "course") or "").lower(),
            str(_entry_value(item, "name") or "").lower(),
        ),
    )


def build_ledger(
    pulled_ts: str,
    due_48_items: list[AssignmentObservation],
    due_7_items: list[AssignmentObservation],
    missing_raw: list[dict],
    course_ids: set[int],
    course_name_by_id: dict[int, str],
    course_snapshot_by_name: dict[str, CourseInfo] | None = None,
    existing_ledger: dict[str, dict] | None = None,
    *,
    source_adapter: str = "canvas",
) -> list[LedgerEntry]:
    """Build the assignment ledger from current observations and previous state."""
    previous = existing_ledger if existing_ledger is not None else {}
    current_observed: dict[str, dict] = {}
    matched_previous_ids: set[str] = set()
    course_snapshot_by_name = course_snapshot_by_name or {}

    for observation in due_48_items:
        merge_current_observation(
            current_observed,
            course=observation.course,
            name=observation.name,
            due_dt=observation.due_at,
            status="due_48h",
            source_key=observation.source_key,
            course_info=course_snapshot_by_name.get(observation.course),
            source_adapter=source_adapter,
        )
    for observation in due_7_items:
        merge_current_observation(
            current_observed,
            course=observation.course,
            name=observation.name,
            due_dt=observation.due_at,
            status="due_7d",
            source_key=observation.source_key,
            course_info=course_snapshot_by_name.get(observation.course),
            source_adapter=source_adapter,
        )
    for item in missing_raw:
        if not isinstance(item, dict):
            continue
        cid = item.get("course_id")
        if course_ids and isinstance(cid, int) and cid not in course_ids:
            continue
        course = course_name_by_id.get(cid, f"course_id:{cid}") if isinstance(cid, int) else "unknown"
        name = str(item.get("name") or item.get("assignment_name") or "Unnamed")
        assignment_ref = item.get("assignment_id")
        if assignment_ref in (None, ""):
            assignment_ref = item.get("id")
        source_key = None
        if isinstance(cid, int) and isinstance(assignment_ref, (int, str)):
            source_key = f"canvas:{cid}:{str(assignment_ref).strip()}"
        merge_current_observation(
            current_observed,
            course=course,
            name=name,
            due_dt=parse_datetime(item.get("due_at")),
            status="missing",
            source_key=source_key,
            course_info=course_snapshot_by_name.get(course),
            source_adapter=source_adapter,
        )

    ledger: list[LedgerEntry] = []
    for item_id, current in current_observed.items():
        previous_id, previous_item = match_entry(
            previous,
            course=str(current.get("course") or ""),
            name=str(current.get("name") or ""),
            source_key=str(current.get("source_key") or "") or None,
            item_id=item_id,
        )
        if previous_id:
            matched_previous_ids.add(previous_id)
        previous_item = previous_item or {}
        entry = current.copy()
        entry["first_seen"] = str(previous_item.get("first_seen") or pulled_ts)
        entry["last_seen"] = pulled_ts
        if not entry.get("due_at") and previous_item.get("due_at"):
            entry["due_at"] = str(previous_item.get("due_at") or "")
            entry["date"] = str(previous_item.get("date") or "")
        entry.setdefault("schema_version", previous_item.get("schema_version") or current.get("schema_version"))
        entry.setdefault("engine_version", previous_item.get("engine_version") or current.get("engine_version"))
        entry["source_adapter"] = str(
            current.get("source_adapter") or previous_item.get("source_adapter") or source_adapter
        )
        if "course_score" not in entry and previous_item.get("course_score") is not None:
            entry["course_score"] = previous_item.get("course_score")
        if not entry.get("course_grade") and previous_item.get("course_grade"):
            entry["course_grade"] = previous_item.get("course_grade")
        ledger.append(ledger_entry_from_mapping(entry, default_source_adapter=source_adapter))

    for item_id, previous_item in previous.items():
        if item_id in current_observed or item_id in matched_previous_ids:
            continue
        carried = previous_item.copy()
        carried["status"] = "not_observed"
        carried["severity_label"] = LEDGER_SEVERITY_LABEL["not_observed"]
        carried["first_seen"] = str(carried.get("first_seen") or carried.get("last_seen") or pulled_ts)
        carried["last_seen"] = str(carried.get("last_seen") or carried.get("first_seen") or pulled_ts)
        carried["source_key"] = str(carried.get("source_key") or "")
        carried["due_at"] = str(carried.get("due_at") or "")
        carried["date"] = str(carried.get("date") or "")
        carried["source_adapter"] = str(carried.get("source_adapter") or source_adapter)
        ledger.append(ledger_entry_from_mapping(carried, default_source_adapter=source_adapter))

    sorted_ledger = sort_ledger(ledger)
    return [
        item
        if isinstance(item, LedgerEntry)
        else ledger_entry_from_mapping(item, default_source_adapter=source_adapter)
        for item in sorted_ledger
    ]


def resolve_repair_pulled_ts(timestamp_path: Path, current_ledger: list[dict]) -> str:
    """Determine the best pulled_ts for artifact repair."""
    if timestamp_path.exists():
        stamp = timestamp_path.read_text(errors="ignore").strip()
        if stamp:
            return stamp

    candidates = []
    for item in current_ledger:
        for key in ("last_seen", "first_seen"):
            value = str(item.get(key) or "").strip()
            if value:
                candidates.append(value)
    if candidates:
        return max(candidates)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
