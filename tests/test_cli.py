"""Tests for duecheck.cli."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from duecheck.cli import main, run_pull, run_repair

from .conftest import make_urlopen


def _make_course(course_id: int, name: str, score: float = 90.0):
    return {
        "id": course_id,
        "name": name,
        "enrollments": [{"computed_current_score": score, "computed_current_grade": "A"}],
    }


def _make_assignment(name: str, due_at: str, submitted: bool = False):
    submission = {"submitted_at": "2026-03-01T00:00:00Z"} if submitted else {}
    return {"name": name, "due_at": due_at, "submission": submission}


def test_main_no_canvas_url():
    with patch.dict("os.environ", {}, clear=True):
        result = main(["--canvas-url", ""])
    assert result == 1


def test_main_no_token():
    with patch.dict("os.environ", {"CANVAS_TOKEN": ""}, clear=True):
        result = main(["--canvas-url", "https://canvas.example.com"])
    assert result == 1


def test_run_pull_success(tmp_path: Path):
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    due_soon = (now + timedelta(hours=12)).isoformat()
    courses = [_make_course(101, "English")]
    assignments = [_make_assignment("Essay 1", due_soon)]
    urlopen = make_urlopen({
        "courses": courses,
        "assignments": assignments,
        "missing_submissions": [],
    })

    summary = run_pull(
        canvas_url="https://canvas.example.com",
        token="fake-token",
        out_dir=tmp_path,
        now=now,
        urlopen_fn=urlopen,
    )
    assert summary["courses"] == 1
    assert (tmp_path / "ledger.json").exists()
    assert (tmp_path / "delta.json").exists()
    assert (tmp_path / "risk.json").exists()
    assert (tmp_path / "changes.md").exists()


def test_run_pull_json_output(tmp_path: Path):
    now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
    courses = [_make_course(101, "English")]
    urlopen = make_urlopen({
        "courses": courses,
        "assignments": [],
        "missing_submissions": [],
    })

    summary = run_pull(
        canvas_url="https://canvas.example.com",
        token="fake-token",
        out_dir=tmp_path,
        now=now,
        urlopen_fn=urlopen,
    )
    assert "courses" in summary
    assert "risk_overall" in summary
    risk = json.loads((tmp_path / "risk.json").read_text())
    assert "overall" in risk


def test_repair_no_ledger(tmp_path: Path):
    result = run_repair(tmp_path)
    assert result["status"] == "skipped"


def test_repair_valid_ledger(tmp_path: Path):
    ledger = [
        {"item_id": "asg_abc", "name": "Essay 1", "course": "English",
         "status": "missing", "due_at": "2026-03-10T23:59:00Z",
         "first_seen": "2026-03-01T00:00:00Z", "last_seen": "2026-03-05T00:00:00Z",
         "date": "2026-03-10", "confidence": "high"},
    ]
    (tmp_path / "ledger.json").write_text(json.dumps(ledger))
    (tmp_path / "pulled_at.txt").write_text("2026-03-05T12:00:00Z")
    result = run_repair(tmp_path)
    assert result["status"] == "repaired"
    assert (tmp_path / "delta.json").exists()
    assert (tmp_path / "changes.md").exists()
