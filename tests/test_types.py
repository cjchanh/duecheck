"""Tests for duecheck.types."""

from datetime import datetime, timezone

from duecheck.types import (
    CourseInfo,
    format_due_at,
    format_due_date,
    ledger_item_id,
    parse_datetime,
)


def test_parse_datetime_iso():
    dt = parse_datetime("2026-03-10T23:59:00Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.tzinfo is not None


def test_parse_datetime_none():
    assert parse_datetime(None) is None
    assert parse_datetime("") is None


def test_parse_datetime_invalid():
    assert parse_datetime("not-a-date") is None


def test_format_due_at():
    dt = datetime(2026, 3, 10, 23, 59, 0, tzinfo=timezone.utc)
    assert format_due_at(dt) == "2026-03-10T23:59:00Z"
    assert format_due_at(None) == ""


def test_format_due_date():
    dt = datetime(2026, 3, 10, 23, 59, 0, tzinfo=timezone.utc)
    assert format_due_date(dt) == "2026-03-10"
    assert format_due_date(None) == ""


def test_ledger_item_id_deterministic():
    id1 = ledger_item_id("English", "Essay 1")
    id2 = ledger_item_id("English", "Essay 1")
    assert id1 == id2
    assert id1.startswith("asg_")


def test_ledger_item_id_case_insensitive():
    id1 = ledger_item_id("English", "Essay 1")
    id2 = ledger_item_id("ENGLISH", "essay 1")
    assert id1 == id2


def test_ledger_item_id_different_inputs():
    id1 = ledger_item_id("English", "Essay 1")
    id2 = ledger_item_id("Philosophy", "Essay 1")
    assert id1 != id2


def test_course_info_frozen():
    c = CourseInfo(id=1, name="Test", slug="TST", score=90.0, grade="A")
    assert c.id == 1
    assert c.name == "Test"
