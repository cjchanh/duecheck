"""Tests for duecheck.ledger."""

import json
from datetime import datetime, timezone
from pathlib import Path

from duecheck.ledger import (
    build_ledger,
    load_existing_ledger,
    merge_current_observation,
    resolve_repair_pulled_ts,
    sort_ledger,
)
from duecheck.types import AssignmentObservation, ledger_item_id


def test_load_existing_ledger_empty(tmp_path: Path):
    assert load_existing_ledger(tmp_path / "nonexistent.json") == {}


def test_load_existing_ledger_valid(tmp_path: Path):
    path = tmp_path / "ledger.json"
    entries = [
        {"name": "Essay 1", "course": "English", "status": "missing", "due_at": "2026-03-10T23:59:00Z"},
    ]
    path.write_text(json.dumps(entries))
    result = load_existing_ledger(path)
    assert len(result) == 1
    key = list(result.keys())[0]
    assert result[key]["name"] == "Essay 1"


def test_load_existing_ledger_bad_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    assert load_existing_ledger(path) == {}


def test_merge_current_observation_new():
    observed: dict[str, dict] = {}
    merge_current_observation(
        observed, course="English", name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc), status="due_48h",
    )
    assert len(observed) == 1
    key = list(observed.keys())[0]
    assert observed[key]["status"] == "due_48h"


def test_merge_current_observation_promotes_source_key_identity():
    observed: dict[str, dict] = {}
    merge_current_observation(
        observed,
        course="English",
        name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc),
        status="due_7d",
    )
    merge_current_observation(
        observed,
        course="English",
        name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc),
        status="missing",
        source_key="canvas:101:555",
    )
    assert len(observed) == 1
    key = list(observed.keys())[0]
    assert key == ledger_item_id("English", "Essay 1", source_key="canvas:101:555")
    assert observed[key]["status"] == "missing"


def test_merge_current_observation_higher_priority_wins():
    observed: dict[str, dict] = {}
    merge_current_observation(
        observed, course="English", name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc), status="due_7d",
    )
    merge_current_observation(
        observed, course="English", name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc), status="missing",
    )
    key = list(observed.keys())[0]
    assert observed[key]["status"] == "missing"


def test_merge_current_observation_lower_priority_no_overwrite():
    observed: dict[str, dict] = {}
    merge_current_observation(
        observed, course="English", name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc), status="missing",
    )
    merge_current_observation(
        observed, course="English", name="Essay 1",
        due_dt=datetime(2026, 3, 10, tzinfo=timezone.utc), status="due_7d",
    )
    key = list(observed.keys())[0]
    assert observed[key]["status"] == "missing"


def test_sort_ledger_active_before_inactive():
    items = [
        {"status": "not_observed", "due_at": "2026-03-01", "course": "A", "name": "X"},
        {"status": "missing", "due_at": "2026-03-05", "course": "A", "name": "Y"},
    ]
    sorted_items = sort_ledger(items)
    assert sorted_items[0]["status"] == "missing"
    assert sorted_items[1]["status"] == "not_observed"


def test_build_ledger_new_items():
    pulled_ts = "2026-03-05T12:00:00Z"
    due_48 = [AssignmentObservation(
        source_key="canvas:101:1",
        due_at=datetime(2026, 3, 6, 23, 59, tzinfo=timezone.utc),
        course="English",
        name="Essay 1",
    )]
    due_7 = [AssignmentObservation(
        source_key="canvas:102:2",
        due_at=datetime(2026, 3, 10, 23, 59, tzinfo=timezone.utc),
        course="Philosophy",
        name="Paper 2",
    )]
    ledger = build_ledger(pulled_ts, due_48, due_7, [], set(), {})
    assert len(ledger) == 2
    statuses = {item["name"]: item["status"] for item in ledger}
    assert statuses["Essay 1"] == "due_48h"
    assert statuses["Paper 2"] == "due_7d"


def test_build_ledger_carries_forward():
    pulled_ts = "2026-03-05T12:00:00Z"
    item_id = ledger_item_id("English", "Old Essay")
    existing = {
        item_id: {
            "item_id": item_id, "name": "Old Essay", "course": "English",
            "status": "missing", "first_seen": "2026-03-01T00:00:00Z",
            "last_seen": "2026-03-04T00:00:00Z", "due_at": "2026-03-02T23:59:00Z",
            "date": "2026-03-02", "confidence": "high",
        }
    }
    ledger = build_ledger(pulled_ts, [], [], [], set(), {}, existing_ledger=existing)
    assert len(ledger) == 1
    assert ledger[0]["status"] == "not_observed"
    assert ledger[0]["first_seen"] == "2026-03-01T00:00:00Z"


def test_build_ledger_matches_legacy_entry_when_source_key_arrives():
    pulled_ts = "2026-03-05T12:00:00Z"
    legacy_item_id = ledger_item_id("English", "Essay 1")
    existing = {
        legacy_item_id: {
            "item_id": legacy_item_id,
            "source_key": "",
            "name": "Essay 1",
            "course": "English",
            "status": "due_7d",
            "first_seen": "2026-03-01T00:00:00Z",
            "last_seen": "2026-03-04T00:00:00Z",
            "due_at": "2026-03-10T23:59:00Z",
            "date": "2026-03-10",
            "confidence": "medium",
        }
    }
    due_48 = [AssignmentObservation(
        source_key="canvas:101:555",
        due_at=datetime(2026, 3, 6, 23, 59, tzinfo=timezone.utc),
        course="English",
        name="Essay 1",
    )]
    ledger = build_ledger(pulled_ts, due_48, [], [], set(), {}, existing_ledger=existing)
    assert len(ledger) == 1
    assert ledger[0]["item_id"] == ledger_item_id("English", "Essay 1", source_key="canvas:101:555")
    assert ledger[0]["first_seen"] == "2026-03-01T00:00:00Z"


def test_resolve_repair_pulled_ts_from_file(tmp_path: Path):
    ts_path = tmp_path / "pulled_at.txt"
    ts_path.write_text("2026-03-05T12:00:00Z")
    result = resolve_repair_pulled_ts(ts_path, [])
    assert result == "2026-03-05T12:00:00Z"


def test_resolve_repair_pulled_ts_from_ledger(tmp_path: Path):
    ts_path = tmp_path / "nonexistent.txt"
    ledger = [{"last_seen": "2026-03-04T00:00:00Z"}, {"last_seen": "2026-03-05T00:00:00Z"}]
    result = resolve_repair_pulled_ts(ts_path, ledger)
    assert result == "2026-03-05T00:00:00Z"
