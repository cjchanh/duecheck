"""Tests for duecheck.adapter."""

from datetime import datetime, timedelta, timezone

from duecheck.adapter import CanvasAdapter
from duecheck.types import LMSAdapter

from .conftest import make_urlopen


def _make_course(course_id: int, name: str, score: float | None = None):
    enrollments = []
    if score is not None:
        enrollments.append({"computed_current_score": score, "computed_current_grade": "B"})
    return {"id": course_id, "name": name, "enrollments": enrollments}


def _make_assignment(name: str, due_at: str | None, submitted: bool = False, assignment_id: int = 1):
    submission = {}
    if submitted:
        submission = {"submitted_at": "2026-03-01T00:00:00Z", "workflow_state": "submitted"}
    return {"id": assignment_id, "name": name, "due_at": due_at, "submission": submission}


def test_adapter_implements_protocol():
    adapter = CanvasAdapter.__new__(CanvasAdapter)
    assert isinstance(adapter, LMSAdapter)


def test_get_courses():
    courses_payload = [
        _make_course(101, "English Composition", 92.0),
        _make_course(102, "Philosophy", 74.0),
    ]
    urlopen = make_urlopen({"courses": courses_payload})
    adapter = CanvasAdapter("https://canvas.example.com", "fake-token", urlopen_fn=urlopen)
    courses = adapter.get_courses()
    assert len(courses) == 2
    assert courses[0].name == "English Composition"
    assert courses[0].score == 92.0


def test_get_courses_with_filter():
    courses_payload = [
        _make_course(101, "English Composition", 92.0),
        _make_course(102, "Philosophy", 74.0),
        _make_course(103, "Chemistry", 88.0),
    ]
    urlopen = make_urlopen({"courses": courses_payload})
    adapter = CanvasAdapter(
        "https://canvas.example.com", "fake-token",
        course_filter=["English", "Philosophy"],
        urlopen_fn=urlopen,
    )
    courses = adapter.get_courses()
    assert len(courses) == 2
    names = {c.name for c in courses}
    assert "Chemistry" not in names


def test_get_courses_caches():
    courses_payload = [_make_course(101, "English Composition")]
    call_count = [0]
    base_urlopen = make_urlopen({"courses": courses_payload})

    def counting_urlopen(req, *args, **kwargs):
        call_count[0] += 1
        return base_urlopen(req, *args, **kwargs)

    adapter = CanvasAdapter("https://canvas.example.com", "fake-token", urlopen_fn=counting_urlopen)
    adapter.get_courses()
    adapter.get_courses()
    assert call_count[0] == 1


def test_get_unsubmitted_assignments():
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    courses_payload = [_make_course(101, "English")]
    assignments_payload = [
        _make_assignment("Essay 1", "2026-03-06T23:59:00Z", submitted=False),
        _make_assignment("Essay 2", "2026-03-10T23:59:00Z", submitted=True),
        _make_assignment("Essay 3", None, submitted=False),
    ]
    urlopen = make_urlopen({"courses": courses_payload, "assignments": assignments_payload})
    adapter = CanvasAdapter("https://canvas.example.com", "fake-token", urlopen_fn=urlopen)
    items = adapter.get_unsubmitted_assignments(101, now)
    assert len(items) == 1
    assert items[0].name == "Essay 1"
    assert items[0].source_key == "canvas:101:1"


def test_get_due_items():
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    courses_payload = [_make_course(101, "English")]
    due_soon = (now + timedelta(hours=12)).isoformat()
    due_5d = (now + timedelta(days=5)).isoformat()
    due_past = (now - timedelta(days=1)).isoformat()
    assignments_payload = [
        _make_assignment("Due Soon", due_soon, submitted=False),
        _make_assignment("Due 5 Days", due_5d, submitted=False),
        _make_assignment("Past Due", due_past, submitted=False),
    ]
    urlopen = make_urlopen({"courses": courses_payload, "assignments": assignments_payload})
    adapter = CanvasAdapter("https://canvas.example.com", "fake-token", urlopen_fn=urlopen)
    due_48h, due_7d = adapter.get_due_items(now)
    assert len(due_48h) == 1
    assert due_48h[0].name == "Due Soon"
    assert len(due_7d) == 1
    assert due_7d[0].name == "Due 5 Days"


def test_get_missing_submissions():
    courses_payload = [_make_course(101, "English")]
    missing_payload = [
        {"name": "Missing 1", "course_id": 101},
        {"name": "Missing 2", "course_id": 999},
    ]
    urlopen = make_urlopen({
        "courses": courses_payload,
        "missing_submissions": missing_payload,
    })
    adapter = CanvasAdapter("https://canvas.example.com", "fake-token", urlopen_fn=urlopen)
    missing = adapter.get_missing_submissions()
    assert len(missing) == 1
    assert missing[0]["name"] == "Missing 1"
