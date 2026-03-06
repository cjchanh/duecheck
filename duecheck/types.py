"""Shared types, constants, and protocols for DueCheck."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, runtime_checkable

ARTIFACT_SCHEMA_VERSION = "1.0"

LEDGER_STATUS_PRIORITY: dict[str, int] = {
    "missing": 3,
    "due_48h": 2,
    "due_7d": 1,
    "not_observed": 0,
}

LEDGER_SEVERITY_LABEL: dict[str, str] = {
    "missing": "high",
    "due_48h": "high",
    "due_7d": "medium",
    "not_observed": "low",
}


def current_engine_version() -> str:
    from . import __version__

    return __version__


class ArtifactRecord:
    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


@dataclass(frozen=True)
class ArtifactMeta(ArtifactRecord):
    schema_version: str = ARTIFACT_SCHEMA_VERSION
    engine_version: str = field(default_factory=current_engine_version)
    source_adapter: str = "canvas"

    @classmethod
    def for_source(cls, source_adapter: str) -> "ArtifactMeta":
        return cls(source_adapter=source_adapter)

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "source_adapter": self.source_adapter,
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
class LedgerEntry(ArtifactRecord):
    item_id: str
    source_key: str
    name: str
    course: str
    status: str
    first_seen: str
    last_seen: str
    due_at: str
    date: str
    severity_label: str
    course_score: float | None = None
    course_grade: str = ""
    schema_version: str = ARTIFACT_SCHEMA_VERSION
    engine_version: str = field(default_factory=current_engine_version)
    source_adapter: str = "canvas"

    def to_dict(self) -> dict[str, str | float | None]:
        payload: dict[str, str | float | None] = {
            "item_id": self.item_id,
            "source_key": self.source_key,
            "name": self.name,
            "course": self.course,
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "due_at": self.due_at,
            "date": self.date,
            "severity_label": self.severity_label,
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "source_adapter": self.source_adapter,
        }
        if self.course_score is not None:
            payload["course_score"] = self.course_score
        if self.course_grade:
            payload["course_grade"] = self.course_grade
        return payload


@dataclass(frozen=True)
class DeltaChange(ArtifactRecord):
    item_id: str
    name: str
    course: str
    change_type: str
    from_status: str
    to_status: str
    from_due_at: str
    to_due_at: str
    due_at_changed: bool
    first_seen: str
    last_seen: str
    severity_label: str
    deadline_change: str = ""

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "course": self.course,
            "change_type": self.change_type,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "from_due_at": self.from_due_at,
            "to_due_at": self.to_due_at,
            "due_at_changed": self.due_at_changed,
            "deadline_change": self.deadline_change,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "severity_label": self.severity_label,
        }


@dataclass(frozen=True)
class DeltaReport(ArtifactRecord):
    meta: ArtifactMeta
    pulled_at: str
    counts: dict[str, int]
    changes: list[DeltaChange]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.meta.to_dict()
        payload.update(
            {
                "pulled_at": self.pulled_at,
                "counts": dict(self.counts),
                "changes": [change.to_dict() for change in self.changes],
            }
        )
        return payload


@dataclass(frozen=True)
class RiskReport(ArtifactRecord):
    meta: ArtifactMeta
    overall: str
    course_risks: dict[str, str]
    missing_risk: str
    flagged_courses: list[str]
    missing_count: int

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.meta.to_dict()
        payload.update(
            {
                "overall": self.overall,
                "course_risks": dict(self.course_risks),
                "missing_risk": self.missing_risk,
                "flagged_courses": list(self.flagged_courses),
                "missing_count": self.missing_count,
            }
        )
        return payload


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


def ledger_entry_from_mapping(
    item: Mapping[str, object],
    *,
    default_source_adapter: str = "canvas",
) -> LedgerEntry:
    name = str(item.get("name") or item.get("assignment_name") or "").strip()
    course = str(item.get("course") or "").strip()
    source_key = str(item.get("source_key") or "")
    due_at = str(item.get("due_at") or "")
    date_text = str(item.get("date") or "")
    if not date_text and due_at:
        parsed = parse_datetime(due_at)
        if parsed is not None:
            date_text = format_due_date(parsed)

    return LedgerEntry(
        item_id=str(item.get("item_id") or ledger_item_id(course, name, source_key=source_key or None)),
        source_key=source_key,
        name=name,
        course=course,
        status=str(item.get("status") or "not_observed"),
        first_seen=str(item.get("first_seen") or item.get("last_seen") or ""),
        last_seen=str(item.get("last_seen") or item.get("first_seen") or ""),
        due_at=due_at,
        date=date_text,
        severity_label=str(
            item.get("severity_label") or item.get("confidence") or "low"
        ),  # migration: accept legacy confidence key
        course_score=float(item["course_score"]) if item.get("course_score") is not None else None,
        course_grade=str(item.get("course_grade") or ""),
        schema_version=str(item.get("schema_version") or ARTIFACT_SCHEMA_VERSION),
        engine_version=str(item.get("engine_version") or current_engine_version()),
        source_adapter=str(item.get("source_adapter") or default_source_adapter),
    )


def delta_change_from_mapping(item: Mapping[str, object]) -> DeltaChange:
    return DeltaChange(
        item_id=str(item.get("item_id") or ""),
        name=str(item.get("name") or ""),
        course=str(item.get("course") or ""),
        change_type=str(item.get("change_type") or ""),
        from_status=str(item.get("from_status") or "absent"),
        to_status=str(item.get("to_status") or "not_observed"),
        from_due_at=str(item.get("from_due_at") or ""),
        to_due_at=str(item.get("to_due_at") or ""),
        due_at_changed=bool(item.get("due_at_changed")),
        deadline_change=str(item.get("deadline_change") or ""),
        first_seen=str(item.get("first_seen") or ""),
        last_seen=str(item.get("last_seen") or ""),
        severity_label=str(item.get("severity_label") or item.get("confidence") or ""),
    )


def delta_report_from_mapping(
    item: Mapping[str, object],
    *,
    default_source_adapter: str = "canvas",
) -> DeltaReport:
    meta = ArtifactMeta(
        schema_version=str(item.get("schema_version") or ARTIFACT_SCHEMA_VERSION),
        engine_version=str(item.get("engine_version") or current_engine_version()),
        source_adapter=str(item.get("source_adapter") or default_source_adapter),
    )
    raw_counts = item.get("counts")
    counts: dict[str, int] = {}
    if isinstance(raw_counts, Mapping):
        for key, value in raw_counts.items():
            counts[str(key)] = int(value)

    raw_changes = item.get("changes")
    changes: list[DeltaChange] = []
    if isinstance(raw_changes, list):
        for change in raw_changes:
            if isinstance(change, Mapping):
                changes.append(delta_change_from_mapping(change))

    return DeltaReport(
        meta=meta,
        pulled_at=str(item.get("pulled_at") or ""),
        counts=counts,
        changes=changes,
    )


def risk_report_from_mapping(
    item: Mapping[str, object],
    *,
    default_source_adapter: str = "canvas",
) -> RiskReport:
    meta = ArtifactMeta(
        schema_version=str(item.get("schema_version") or ARTIFACT_SCHEMA_VERSION),
        engine_version=str(item.get("engine_version") or current_engine_version()),
        source_adapter=str(item.get("source_adapter") or default_source_adapter),
    )
    raw_course_risks = item.get("course_risks")
    course_risks: dict[str, str] = {}
    if isinstance(raw_course_risks, Mapping):
        for key, value in raw_course_risks.items():
            course_risks[str(key)] = str(value)

    raw_flagged = item.get("flagged_courses")
    flagged_courses = [str(course) for course in raw_flagged] if isinstance(raw_flagged, list) else []

    return RiskReport(
        meta=meta,
        overall=str(item.get("overall") or "UNKNOWN"),
        course_risks=course_risks,
        missing_risk=str(item.get("missing_risk") or "UNKNOWN"),
        flagged_courses=flagged_courses,
        missing_count=int(item.get("missing_count") or 0),
    )


def serialize_payload(payload: Any) -> Any:
    if hasattr(payload, "to_dict"):
        return serialize_payload(payload.to_dict())
    if isinstance(payload, list):
        return [serialize_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [serialize_payload(item) for item in payload]
    if isinstance(payload, Mapping):
        return {str(key): serialize_payload(value) for key, value in payload.items()}
    return payload
