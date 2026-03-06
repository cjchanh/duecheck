"""Tests for duecheck.risk."""

from datetime import datetime, timedelta, timezone

from duecheck.risk import (
    aggregate_risk,
    compute_overall_risk,
    score_course_risk,
    score_missing_risk,
)
from duecheck.types import CourseInfo


def test_score_course_risk_high():
    c = CourseInfo(id=1, name="Test", slug="T", score=65.0, grade="D")
    assert score_course_risk(c) == "HIGH"


def test_score_course_risk_medium():
    c = CourseInfo(id=1, name="Test", slug="T", score=74.0, grade="C")
    assert score_course_risk(c) == "MEDIUM"


def test_score_course_risk_low():
    c = CourseInfo(id=1, name="Test", slug="T", score=92.0, grade="A")
    assert score_course_risk(c) == "LOW"


def test_score_course_risk_none():
    c = CourseInfo(id=1, name="Test", slug="T", score=None, grade=None)
    assert score_course_risk(c) == "MEDIUM"


def test_score_missing_risk_empty():
    assert score_missing_risk([]) == "LOW"


def test_score_missing_risk_stale():
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    items = [
        {"due_at": (now - timedelta(days=5)).isoformat()},
        {"due_at": (now - timedelta(days=6)).isoformat()},
        {"due_at": (now - timedelta(days=7)).isoformat()},
    ]
    assert score_missing_risk(items, now) == "HIGH"


def test_score_missing_risk_one_stale():
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    items = [{"due_at": (now - timedelta(days=5)).isoformat()}]
    assert score_missing_risk(items, now) == "MEDIUM"


def test_score_missing_risk_recent():
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    items = [{"due_at": (now - timedelta(hours=12)).isoformat()}]
    assert score_missing_risk(items, now) == "LOW"


def test_aggregate_risk_highest_wins():
    assert aggregate_risk("LOW", "MEDIUM", "HIGH") == "HIGH"
    assert aggregate_risk("LOW", "MEDIUM") == "MEDIUM"
    assert aggregate_risk("LOW", "LOW") == "LOW"


def test_aggregate_risk_empty():
    assert aggregate_risk() == "UNKNOWN"


def test_compute_overall_risk():
    courses = [
        CourseInfo(id=1, name="Good", slug="G", score=92.0, grade="A"),
        CourseInfo(id=2, name="Bad", slug="B", score=65.0, grade="D"),
    ]
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    result = compute_overall_risk(courses, [], now)
    assert result["overall"] == "HIGH"
    assert result["course_risks"]["Bad"] == "HIGH"
    assert result["course_risks"]["Good"] == "LOW"
    assert "Bad" in result["flagged_courses"]
