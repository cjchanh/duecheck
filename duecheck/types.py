"""Shared types, constants, and protocols for DueCheck."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol, runtime_checkable

LEDGER_STATUS_PRIORITY: dict[str, int] = {
    "missing": 3,
    "due_48h": 2,
    "due_7d": 1,
    "not_observed": 0,
}

LEDGER_CONFIDENCE: dict[str, str] = {
    "missing": "high",
    "due_48h": "high",
    "due_7d": "medium",
    "not_observed": "low",
}


@dataclass(frozen=True)
class CourseInfo:
    id: int
    name: str
    slug: str
    score: float | None
    grade: str | None


@dataclass(frozen=True)
class AssignmentObservation:
    source_key: str | None
    due_at: datetime
    course: str
    name: str


@dataclass(frozen=True)
class LedgerEntry:
    item_id: str
    source_key: str
    name: str
    course: str
    status: str
    first_seen: str
    last_seen: str
    due_at: str
    date: str
    confidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "item_id": self.item_id,
            "source_key": self.source_key,
            "name": self.name,
            "course": self.course,
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "due_at": self.due_at,
            "date": self.date,
            "confidence": self.confidence,
        }


@runtime_checkable
class LMSAdapter(Protocol):
    """Minimal protocol for LMS data access."""

    def get_courses(self) -> list[CourseInfo]: ...

    def get_assignments(self, course_id: int) -> list[dict]: ...

    def get_missing_submissions(self) -> list[dict]: ...


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string, handling Z suffix."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_due_at(due_dt: datetime | None) -> str:
    if due_dt is None:
        return ""
    return due_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_due_date(due_dt: datetime | None) -> str:
    if due_dt is None:
        return ""
    return due_dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def normalize_identity_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).strip()


def ledger_item_id(course: str, name: str, *, source_key: str | None = None) -> str:
    if source_key:
        key = "src::" + normalize_identity_text(source_key)
    else:
        key = f"{normalize_identity_text(course)}::{normalize_identity_text(name)}"
    return "asg_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def ledger_item_candidates(course: str, name: str, *, source_key: str | None = None) -> list[str]:
    candidates: list[str] = []
    if source_key:
        candidates.append(ledger_item_id(course, name, source_key=source_key))
    legacy_id = ledger_item_id(course, name)
    if legacy_id not in candidates:
        candidates.append(legacy_id)
    return candidates


def match_entry(
    entries: Mapping[str, dict],
    *,
    course: str,
    name: str,
    source_key: str | None = None,
    item_id: str | None = None,
) -> tuple[str | None, dict | None]:
    candidate_ids: list[str] = []
    if item_id:
        candidate_ids.append(item_id)
    for candidate_id in ledger_item_candidates(course, name, source_key=source_key):
        if candidate_id not in candidate_ids:
            candidate_ids.append(candidate_id)

    for candidate_id in candidate_ids:
        entry = entries.get(candidate_id)
        if entry is not None:
            return candidate_id, entry

    norm_course = normalize_identity_text(course)
    norm_name = normalize_identity_text(name)
    for candidate_id, entry in entries.items():
        if normalize_identity_text(str(entry.get("course") or "")) != norm_course:
            continue
        if normalize_identity_text(str(entry.get("name") or "")) != norm_name:
            continue
        return candidate_id, entry

    return (None, None)
