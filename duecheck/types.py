"""Shared types, constants, and protocols for DueCheck."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

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
class LedgerEntry:
    item_id: str
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


def ledger_item_id(course: str, name: str) -> str:
    key = re.sub(r"\s+", " ", f"{course.strip().lower()}::{name.strip().lower()}").strip()
    return "asg_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
