"""Assignment ledger: persistent state tracking across sync runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .types import (
    LEDGER_CONFIDENCE,
    LEDGER_STATUS_PRIORITY,
    format_due_at,
    format_due_date,
    ledger_item_id,
    parse_datetime,
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
        name = str(item.get("name") or item.get("assignment_name") or "").strip()
        course = str(item.get("course") or "").strip()
        if not name or not course:
            continue
        item_id = str(item.get("item_id") or ledger_item_id(course, name))
        due_at = str(item.get("due_at") or "")
        date_text = str(item.get("date") or "")
        if not date_text and due_at:
            parsed = parse_datetime(due_at)
            if parsed is not None:
                date_text = format_due_date(parsed)
        current = {
            "item_id": item_id,
            "name": name,
            "course": course,
            "status": str(item.get("status") or "not_observed"),
            "first_seen": str(item.get("first_seen") or item.get("last_seen") or ""),
            "last_seen": str(item.get("last_seen") or item.get("first_seen") or ""),
            "due_at": due_at,
            "date": date_text,
            "confidence": str(item.get("confidence") or "low"),
        }
        previous = existing.get(item_id)
        if previous is None or current["last_seen"] >= previous.get("last_seen", ""):
            existing[item_id] = current
    return existing


def merge_current_observation(
    observed: dict[str, dict],
    *,
    course: str,
    name: str,
    due_dt: datetime | None,
    status: str,
) -> None:
    """Merge a single observation into the current observed set."""
    item_id = ledger_item_id(course, name)
    candidate = {
        "item_id": item_id,
        "name": name,
        "course": course,
        "status": status,
        "due_at": format_due_at(due_dt),
        "date": format_due_date(due_dt),
        "confidence": LEDGER_CONFIDENCE[status],
    }
    current = observed.get(item_id)
    if current is None:
        observed[item_id] = candidate
        return
    if LEDGER_STATUS_PRIORITY[status] > LEDGER_STATUS_PRIORITY[current["status"]]:
        observed[item_id] = candidate
        return
    if not current.get("due_at") and candidate["due_at"]:
        current["due_at"] = candidate["due_at"]
        current["date"] = candidate["date"]


def sort_ledger(ledger: list[dict]) -> list[dict]:
    """Sort ledger entries: active first by due date, then inactive."""
    return sorted(
        ledger,
        key=lambda item: (
            1 if item.get("status") == "not_observed" else 0,
            item.get("due_at") or item.get("date") or "9999-12-31T23:59:59Z",
            str(item.get("course") or "").lower(),
            str(item.get("name") or "").lower(),
        ),
    )


def build_ledger(
    pulled_ts: str,
    due_48_items: list[tuple[datetime, str, str]],
    due_7_items: list[tuple[datetime, str, str]],
    missing_raw: list[dict],
    course_ids: set[int],
    course_name_by_id: dict[int, str],
    existing_ledger: dict[str, dict] | None = None,
) -> list[dict]:
    """Build the assignment ledger from current observations and previous state."""
    previous = existing_ledger if existing_ledger is not None else {}
    current_observed: dict[str, dict] = {}

    for due_dt, course, name in due_48_items:
        merge_current_observation(current_observed, course=course, name=name, due_dt=due_dt, status="due_48h")
    for due_dt, course, name in due_7_items:
        merge_current_observation(current_observed, course=course, name=name, due_dt=due_dt, status="due_7d")
    for item in missing_raw:
        if not isinstance(item, dict):
            continue
        cid = item.get("course_id")
        if course_ids and isinstance(cid, int) and cid not in course_ids:
            continue
        course = course_name_by_id.get(cid, f"course_id:{cid}") if isinstance(cid, int) else "unknown"
        name = str(item.get("name") or item.get("assignment_name") or "Unnamed")
        merge_current_observation(
            current_observed,
            course=course,
            name=name,
            due_dt=parse_datetime(item.get("due_at")),
            status="missing",
        )

    ledger: list[dict] = []
    for item_id, current in current_observed.items():
        previous_item = previous.get(item_id, {})
        entry = current.copy()
        entry["first_seen"] = str(previous_item.get("first_seen") or pulled_ts)
        entry["last_seen"] = pulled_ts
        if not entry.get("due_at") and previous_item.get("due_at"):
            entry["due_at"] = str(previous_item.get("due_at") or "")
            entry["date"] = str(previous_item.get("date") or "")
        ledger.append(entry)

    for item_id, previous_item in previous.items():
        if item_id in current_observed:
            continue
        carried = previous_item.copy()
        carried["status"] = "not_observed"
        carried["confidence"] = LEDGER_CONFIDENCE["not_observed"]
        carried["first_seen"] = str(carried.get("first_seen") or carried.get("last_seen") or pulled_ts)
        carried["last_seen"] = str(carried.get("last_seen") or carried.get("first_seen") or pulled_ts)
        carried["due_at"] = str(carried.get("due_at") or "")
        carried["date"] = str(carried.get("date") or "")
        ledger.append(carried)

    return sort_ledger(ledger)


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
