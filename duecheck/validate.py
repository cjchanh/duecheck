"""Stdlib-only artifact validation for DueCheck outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .types import (
    ARTIFACT_SCHEMA_VERSION,
    delta_report_from_mapping,
    ledger_entry_from_mapping,
    risk_report_from_mapping,
    serialize_payload,
)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse {path.name}") from exc


def _require_mapping(item: object, label: str, errors: list[str]) -> Mapping[str, object] | None:
    if not isinstance(item, Mapping):
        errors.append(f"{label}: expected object")
        return None
    return item


def _validate_meta(data: Mapping[str, object], label: str, errors: list[str]) -> None:
    schema_version = str(data.get("schema_version") or "")
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        errors.append(
            f"{label}.schema_version: expected {ARTIFACT_SCHEMA_VERSION}, got {schema_version or 'missing'}"
        )
    for key in ("engine_version", "source_adapter"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}.{key}: expected non-empty string")


def validate_ledger(data: list) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, list):
        return ["ledger: expected list"]

    for index, item in enumerate(data):
        mapping = _require_mapping(item, f"ledger[{index}]", errors)
        if mapping is None:
            continue
        entry = serialize_payload(ledger_entry_from_mapping(mapping))
        _validate_meta(entry, f"ledger[{index}]", errors)
        for key in (
            "item_id",
            "name",
            "course",
            "status",
            "first_seen",
            "last_seen",
            "due_at",
            "date",
            "severity_label",
        ):
            value = entry.get(key)
            if not isinstance(value, str):
                errors.append(f"ledger[{index}].{key}: expected string")
                continue
            if key in {"item_id", "name", "course", "status", "severity_label"} and not value:
                errors.append(f"ledger[{index}].{key}: expected non-empty string")
    return errors


def validate_delta(data: dict) -> list[str]:
    if not isinstance(data, Mapping):
        return ["delta: expected object"]

    errors: list[str] = []
    payload = serialize_payload(delta_report_from_mapping(data))
    _validate_meta(payload, "delta", errors)

    pulled_at = payload.get("pulled_at")
    if not isinstance(pulled_at, str) or not pulled_at:
        errors.append("delta.pulled_at: expected non-empty string")

    counts = payload.get("counts")
    if not isinstance(counts, Mapping):
        errors.append("delta.counts: expected object")
    else:
        for key, value in counts.items():
            if not isinstance(key, str):
                errors.append("delta.counts: expected string keys")
            if not isinstance(value, int):
                errors.append(f"delta.counts.{key}: expected integer")

    changes = payload.get("changes")
    if not isinstance(changes, list):
        errors.append("delta.changes: expected list")
    else:
        for index, change in enumerate(changes):
            mapping = _require_mapping(change, f"delta.changes[{index}]", errors)
            if mapping is None:
                continue
            for key in (
                "item_id",
                "name",
                "course",
                "change_type",
                "from_status",
                "to_status",
                "from_due_at",
                "to_due_at",
                "first_seen",
                "last_seen",
                "severity_label",
                "deadline_change",
            ):
                value = mapping.get(key)
                if not isinstance(value, str):
                    errors.append(f"delta.changes[{index}].{key}: expected string")
                    continue
                if key in {"item_id", "name", "course", "change_type", "to_status", "severity_label"} and not value:
                    errors.append(f"delta.changes[{index}].{key}: expected non-empty string")
            if not isinstance(mapping.get("due_at_changed"), bool):
                errors.append(f"delta.changes[{index}].due_at_changed: expected bool")

    return errors


def validate_risk(data: dict) -> list[str]:
    if not isinstance(data, Mapping):
        return ["risk: expected object"]

    errors: list[str] = []
    payload = serialize_payload(risk_report_from_mapping(data))
    _validate_meta(payload, "risk", errors)

    for key in ("overall", "missing_risk"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"risk.{key}: expected non-empty string")

    course_risks = payload.get("course_risks")
    if not isinstance(course_risks, Mapping):
        errors.append("risk.course_risks: expected object")
    else:
        for key, value in course_risks.items():
            if not isinstance(key, str) or not key:
                errors.append("risk.course_risks: expected non-empty string keys")
            if not isinstance(value, str) or not value:
                errors.append(f"risk.course_risks.{key}: expected non-empty string")

    flagged_courses = payload.get("flagged_courses")
    if not isinstance(flagged_courses, list):
        errors.append("risk.flagged_courses: expected list")
    else:
        for index, item in enumerate(flagged_courses):
            if not isinstance(item, str) or not item:
                errors.append(f"risk.flagged_courses[{index}]: expected non-empty string")

    missing_count = payload.get("missing_count")
    if not isinstance(missing_count, int):
        errors.append("risk.missing_count: expected integer")

    return errors


def validate_payloads(ledger: list, delta: dict, risk: dict) -> dict[str, list[str]]:
    return {
        "ledger": validate_ledger(ledger),
        "delta": validate_delta(delta),
        "risk": validate_risk(risk),
    }


def validate_artifacts(out_dir: Path) -> dict[str, list[str]]:
    ledger = _load_json(out_dir / "ledger.json")
    delta = _load_json(out_dir / "delta.json")
    risk = _load_json(out_dir / "risk.json")
    if not isinstance(ledger, list):
        return {
            "ledger": ["ledger: expected list"],
            "delta": validate_delta(delta if isinstance(delta, dict) else {}),
            "risk": validate_risk(risk if isinstance(risk, dict) else {}),
        }
    return validate_payloads(
        ledger,
        delta if isinstance(delta, dict) else {},
        risk if isinstance(risk, dict) else {},
    )
