"""Artifact redaction helpers for safe bug-report bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .delta import render_delta_markdown
from .types import (
    ArtifactMeta,
    DeltaChange,
    DeltaReport,
    LedgerEntry,
    RiskReport,
    delta_report_from_mapping,
    ledger_entry_from_mapping,
    ledger_item_id,
    risk_report_from_mapping,
)


@dataclass(frozen=True)
class RedactedBundle:
    pulled_at: str
    ledger: list[LedgerEntry]
    delta: DeltaReport
    risk: RiskReport
    changes_md: str


def _load_json(path: Path) -> dict | list:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse {path.name}") from exc
    if not isinstance(payload, (dict, list)):
        raise RuntimeError(f"Unexpected payload shape for {path.name}")
    return payload


def _sorted_unique(values: set[str]) -> list[str]:
    return sorted(values, key=lambda item: (item.lower(), item))


def _course_map(ledger: list[LedgerEntry], delta: DeltaReport, risk: RiskReport) -> dict[str, str]:
    raw_names: set[str] = set()
    raw_names.update(entry.course for entry in ledger if entry.course)
    raw_names.update(change.course for change in delta.changes if change.course)
    raw_names.update(course for course in risk.course_risks if course)
    raw_names.update(course for course in risk.flagged_courses if course)
    return {name: f"Course {index}" for index, name in enumerate(_sorted_unique(raw_names), start=1)}


def _assignment_map(ledger: list[LedgerEntry], delta: DeltaReport) -> dict[tuple[str, str], str]:
    identities: set[tuple[str, str]] = set()
    identities.update((entry.course, entry.name) for entry in ledger if entry.name)
    identities.update((change.course, change.name) for change in delta.changes if change.name)
    ordered = sorted(identities, key=lambda item: (item[0].lower(), item[1].lower(), item[0], item[1]))
    return {
        identity: f"Assignment {index}"
        for index, identity in enumerate(ordered, start=1)
    }


def _source_key_map(ledger: list[LedgerEntry]) -> dict[str, str]:
    raw_keys = {entry.source_key for entry in ledger if entry.source_key}
    return {
        source_key: f"redacted:{index:04d}"
        for index, source_key in enumerate(_sorted_unique(raw_keys), start=1)
    }


def build_redacted_bundle(out_dir: Path) -> RedactedBundle:
    raw_ledger = _load_json(out_dir / "ledger.json")
    raw_delta = _load_json(out_dir / "delta.json")
    raw_risk = _load_json(out_dir / "risk.json")
    if not isinstance(raw_ledger, list):
        raise RuntimeError("ledger.json must be a list")
    if not isinstance(raw_delta, dict):
        raise RuntimeError("delta.json must be an object")
    if not isinstance(raw_risk, dict):
        raise RuntimeError("risk.json must be an object")

    try:
        pulled_at = (out_dir / "pulled_at.txt").read_text(errors="ignore").strip()
    except OSError as exc:
        raise RuntimeError("Failed to read pulled_at.txt") from exc
    if not pulled_at:
        raise RuntimeError("pulled_at.txt is empty")

    ledger = [
        ledger_entry_from_mapping(item, default_source_adapter="redacted")
        for item in raw_ledger
        if isinstance(item, dict)
    ]
    delta = delta_report_from_mapping(raw_delta, default_source_adapter="redacted")
    risk = risk_report_from_mapping(raw_risk, default_source_adapter="redacted")

    course_map = _course_map(ledger, delta, risk)
    assignment_map = _assignment_map(ledger, delta)
    source_map = _source_key_map(ledger)

    redacted_ledger: list[LedgerEntry] = []
    for entry in ledger:
        redacted_course = course_map.get(entry.course, "Course")
        redacted_name = assignment_map.get((entry.course, entry.name), "Assignment")
        redacted_source_key = source_map.get(entry.source_key, "")
        redacted_item_id = ledger_item_id(
            redacted_course,
            redacted_name,
            source_key=redacted_source_key or None,
        )
        redacted_ledger.append(
            LedgerEntry(
                item_id=redacted_item_id,
                source_key=redacted_source_key,
                name=redacted_name,
                course=redacted_course,
                status=entry.status,
                first_seen=entry.first_seen,
                last_seen=entry.last_seen,
                due_at=entry.due_at,
                date=entry.date,
                severity_label=entry.severity_label,
                course_score=entry.course_score,
                course_grade=entry.course_grade,
                schema_version=entry.schema_version,
                engine_version=entry.engine_version,
                source_adapter=entry.source_adapter,
            )
        )

    redacted_changes: list[DeltaChange] = []
    for change in delta.changes:
        redacted_course = course_map.get(change.course, "Course")
        redacted_name = assignment_map.get((change.course, change.name), "Assignment")
        redacted_source_key = source_map.get(
            next(
                (
                    entry.source_key
                    for entry in ledger
                    if entry.course == change.course and entry.name == change.name and entry.source_key
                ),
                "",
            ),
            "",
        )
        redacted_item_id = ledger_item_id(
            redacted_course,
            redacted_name,
            source_key=redacted_source_key or None,
        )
        redacted_changes.append(
            DeltaChange(
                item_id=redacted_item_id,
                name=redacted_name,
                course=redacted_course,
                change_type=change.change_type,
                from_status=change.from_status,
                to_status=change.to_status,
                from_due_at=change.from_due_at,
                to_due_at=change.to_due_at,
                due_at_changed=change.due_at_changed,
                deadline_change=change.deadline_change,
                first_seen=change.first_seen,
                last_seen=change.last_seen,
                severity_label=change.severity_label,
            )
        )

    redacted_delta = DeltaReport(
        meta=ArtifactMeta(
            schema_version=delta.meta.schema_version,
            engine_version=delta.meta.engine_version,
            source_adapter=delta.meta.source_adapter,
        ),
        pulled_at=delta.pulled_at,
        counts=dict(delta.counts),
        changes=redacted_changes,
    )
    redacted_risk = RiskReport(
        meta=ArtifactMeta(
            schema_version=risk.meta.schema_version,
            engine_version=risk.meta.engine_version,
            source_adapter=risk.meta.source_adapter,
        ),
        overall=risk.overall,
        course_risks={
            course_map.get(course_name, "Course"): level
            for course_name, level in risk.course_risks.items()
        },
        missing_risk=risk.missing_risk,
        flagged_courses=[course_map.get(course_name, "Course") for course_name in risk.flagged_courses],
        missing_count=risk.missing_count,
    )
    changes_md = render_delta_markdown(redacted_delta, pulled_at)

    return RedactedBundle(
        pulled_at=pulled_at,
        ledger=redacted_ledger,
        delta=redacted_delta,
        risk=redacted_risk,
        changes_md=changes_md,
    )
