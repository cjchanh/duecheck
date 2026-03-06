"""Tests for duecheck.delta."""

from duecheck.delta import build_delta, render_delta_markdown
from duecheck.types import ledger_item_id


def _entry(name: str, course: str, status: str, due_at: str = "") -> dict:
    item_id = ledger_item_id(course, name)
    return {
        "item_id": item_id,
        "name": name,
        "course": course,
        "status": status,
        "due_at": due_at,
        "first_seen": "2026-03-01T00:00:00Z",
        "last_seen": "2026-03-05T00:00:00Z",
        "severity_label": "high",
    }


def test_build_delta_new_items():
    previous: dict[str, dict] = {}
    current = [_entry("Essay 1", "English", "missing")]
    delta = build_delta(previous, current, "2026-03-05T12:00:00Z")
    assert delta["counts"]["new"] == 1
    assert len(delta["changes"]) == 1
    assert delta["changes"][0]["change_type"] == "new"


def test_build_delta_cleared():
    entry = _entry("Essay 1", "English", "not_observed")
    item_id = entry["item_id"]
    previous = {item_id: {**entry, "status": "missing"}}
    current = [entry]
    delta = build_delta(previous, current, "2026-03-05T12:00:00Z")
    assert delta["counts"]["cleared"] == 1


def test_build_delta_became_missing():
    entry = _entry("Essay 1", "English", "missing")
    item_id = entry["item_id"]
    previous = {item_id: {**entry, "status": "due_7d"}}
    current = [entry]
    delta = build_delta(previous, current, "2026-03-05T12:00:00Z")
    assert delta["counts"]["became_missing"] == 1


def test_build_delta_de_escalated():
    entry = _entry("Essay 1", "English", "due_7d")
    item_id = entry["item_id"]
    previous = {item_id: {**entry, "status": "missing"}}
    current = [entry]
    delta = build_delta(previous, current, "2026-03-05T12:00:00Z")
    assert delta["counts"]["de_escalated"] == 1


def test_build_delta_matches_previous_entry_after_identity_upgrade():
    current = [_entry("Essay 1", "English", "missing")]
    current[0]["source_key"] = "canvas:101:555"
    current[0]["item_id"] = ledger_item_id("English", "Essay 1", source_key="canvas:101:555")

    legacy_item_id = ledger_item_id("English", "Essay 1")
    previous = {
        legacy_item_id: {
            **_entry("Essay 1", "English", "due_7d"),
            "item_id": legacy_item_id,
            "source_key": "",
        }
    }
    delta = build_delta(previous, current, "2026-03-05T12:00:00Z")
    assert delta["counts"]["became_missing"] == 1


def test_build_delta_unchanged_active():
    entry = _entry("Essay 1", "English", "missing")
    item_id = entry["item_id"]
    previous = {item_id: entry.copy()}
    current = [entry]
    delta = build_delta(previous, current, "2026-03-05T12:00:00Z")
    assert delta["counts"]["unchanged_active"] == 1


def test_render_delta_markdown():
    delta = {
        "counts": {
            "new": 1,
            "reactivated": 0,
            "became_missing": 0,
            "escalated": 0,
            "de_escalated": 0,
            "cleared": 0,
            "unchanged_active": 0,
            "unchanged_inactive": 0,
            "deadline_moved_earlier": 0,
            "deadline_moved_later": 0,
        },
        "changes": [{
            "item_id": "asg_abc123", "name": "Essay 1", "course": "English",
            "change_type": "new", "from_status": "absent", "to_status": "missing",
            "from_due_at": "", "to_due_at": "2026-03-10T23:59:00Z",
            "due_at_changed": True, "deadline_change": "", "first_seen": "", "last_seen": "", "severity_label": "high",
        }],
    }
    md = render_delta_markdown(delta, "2026-03-05T12:00:00Z")
    assert "# Assignment Changes" in md
    assert "English" in md
    assert "Essay 1" in md
    assert "- new: 1" in md


def test_deadline_move_detected():
    entry = _entry("Essay 1", "English", "due_7d", due_at="2026-03-12T12:00:00Z")
    item_id = entry["item_id"]
    previous = {
        item_id: {
            **entry,
            "status": "due_7d",
            "due_at": "2026-03-10T12:00:00Z",
        }
    }
    delta = build_delta(previous, [entry], "2026-03-05T12:00:00Z")
    assert delta["counts"]["deadline_moved_later"] == 1
    assert delta["changes"][0]["deadline_change"] == "deadline_moved_later"


def test_became_missing_classified_correctly():
    entry = _entry("Essay 1", "English", "missing", due_at="2026-03-10T12:00:00Z")
    item_id = entry["item_id"]
    previous = {
        item_id: {
            **entry,
            "status": "due_48h",
        }
    }
    delta = build_delta(previous, [entry], "2026-03-05T12:00:00Z")
    assert delta["counts"]["became_missing"] == 1
    assert delta["counts"]["escalated"] == 0
    assert delta["changes"][0]["change_type"] == "became_missing"
