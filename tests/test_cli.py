"""Tests for duecheck.cli."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from duecheck.cli import main, run_demo, run_pull, run_repair, run_report

from .conftest import make_urlopen


def _make_course(course_id: int, name: str, score: float = 90.0):
    return {
        "id": course_id,
        "name": name,
        "enrollments": [{"computed_current_score": score, "computed_current_grade": "A"}],
    }


def _make_assignment(name: str, due_at: str, submitted: bool = False, assignment_id: int = 1):
    submission = {"submitted_at": "2026-03-01T00:00:00Z"} if submitted else {}
    return {"id": assignment_id, "name": name, "due_at": due_at, "submission": submission}


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
    assert (tmp_path / "runs" / "2026-03-05T12-00-00Z" / "ledger.json").exists()


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


def test_repair_requires_prior_snapshot(tmp_path: Path):
    ledger = [{
        "item_id": "asg_abc",
        "source_key": "",
        "name": "Essay 1",
        "course": "English",
        "status": "missing",
        "due_at": "2026-03-10T23:59:00Z",
        "first_seen": "2026-03-01T00:00:00Z",
        "last_seen": "2026-03-05T00:00:00Z",
        "date": "2026-03-10",
        "confidence": "high",
    }]
    (tmp_path / "ledger.json").write_text(json.dumps(ledger))
    (tmp_path / "pulled_at.txt").write_text("2026-03-05T12:00:00Z")
    result = run_repair(tmp_path)
    assert result["status"] == "skipped"


def test_repair_uses_latest_prior_snapshot(tmp_path: Path):
    previous_run = tmp_path / "runs" / "2026-03-04T12-00-00Z"
    previous_run.mkdir(parents=True)
    previous_ledger = [{
        "item_id": "asg_abc",
        "source_key": "canvas:101:1",
        "name": "Essay 1",
        "course": "English",
        "status": "due_7d",
        "due_at": "2026-03-10T23:59:00Z",
        "first_seen": "2026-03-01T00:00:00Z",
        "last_seen": "2026-03-04T12:00:00Z",
        "date": "2026-03-10",
        "confidence": "medium",
    }]
    (previous_run / "ledger.json").write_text(json.dumps(previous_ledger))
    (previous_run / "pulled_at.txt").write_text("2026-03-04T12:00:00Z\n")

    current_ledger = [{
        "item_id": "asg_abc",
        "source_key": "canvas:101:1",
        "name": "Essay 1",
        "course": "English",
        "status": "missing",
        "due_at": "2026-03-10T23:59:00Z",
        "first_seen": "2026-03-01T00:00:00Z",
        "last_seen": "2026-03-05T12:00:00Z",
        "date": "2026-03-10",
        "confidence": "high",
    }]
    (tmp_path / "ledger.json").write_text(json.dumps(current_ledger))
    (tmp_path / "pulled_at.txt").write_text("2026-03-05T12:00:00Z\n")

    result = run_repair(tmp_path)
    assert result["status"] == "repaired"
    assert result["counts"]["became_missing"] == 1
    delta = json.loads((tmp_path / "delta.json").read_text())
    assert delta["counts"]["became_missing"] == 1


def test_run_demo_writes_artifacts_and_report(tmp_path: Path):
    result = run_demo(tmp_path)
    assert result["status"] == "demo_ready"
    assert (tmp_path / "ledger.json").exists()
    assert (tmp_path / "delta.json").exists()
    assert (tmp_path / "risk.json").exists()
    assert (tmp_path / "changes.md").exists()
    assert (tmp_path / "report.html").exists()


def test_run_demo_includes_deadline_and_became_missing_examples(tmp_path: Path):
    run_demo(tmp_path)
    delta = json.loads((tmp_path / "delta.json").read_text())
    change_types = {item["change_type"] for item in delta["changes"]}
    deadline_changes = {item["deadline_change"] for item in delta["changes"]}

    assert "became_missing" in change_types
    assert "deadline_moved_later" in deadline_changes


def test_run_report_writes_html(tmp_path: Path):
    run_demo(tmp_path)
    output_path = tmp_path / "site" / "index.html"
    result = run_report(tmp_path, html=True, output_path=output_path)
    assert result["status"] == "report_ready"
    assert output_path.exists()
    html = output_path.read_text()
    assert "What changed since your last check." in html


def test_open_flag_noop_without_flag(tmp_path: Path):
    with patch("duecheck.cli.webbrowser.open") as open_browser:
        run_demo(tmp_path)
    open_browser.assert_not_called()


def test_run_demo_open_flag_calls_browser(tmp_path: Path):
    with patch("duecheck.cli.webbrowser.open", return_value=True) as open_browser:
        result = run_demo(tmp_path, open_browser=True)

    open_browser.assert_called_once()
    assert result["opened_browser"] is True


def test_run_report_open_flag_calls_browser(tmp_path: Path):
    run_demo(tmp_path)
    output_path = tmp_path / "site" / "index.html"

    with patch("duecheck.cli.webbrowser.open", return_value=True) as open_browser:
        result = run_report(tmp_path, html=True, output_path=output_path, open_browser=True)

    open_browser.assert_called_once()
    assert result["opened_browser"] is True


def test_main_report_requires_html(tmp_path: Path):
    run_demo(tmp_path)
    result = main(["report", "--out-dir", str(tmp_path)])
    assert result == 1


def test_fail_on_high_exits_2(tmp_path: Path):
    def fake_run_pull(**kwargs):
        out_dir = kwargs["out_dir"]
        (out_dir / "delta.json").write_text(json.dumps({"counts": {"escalated": 0}}))
        (out_dir / "risk.json").write_text(json.dumps({"overall": "HIGH"}))
        return {
            "courses": 1,
            "due_48h": 0,
            "due_7d": 0,
            "missing": 0,
            "risk_overall": "HIGH",
        }

    with patch.dict("os.environ", {"CANVAS_TOKEN": "fake-token"}, clear=True):
        with patch("duecheck.cli.run_pull", side_effect=fake_run_pull):
            result = main(
                [
                    "--canvas-url",
                    "https://canvas.example.com",
                    "--out-dir",
                    str(tmp_path),
                    "--fail-on",
                    "HIGH",
                ]
            )
    assert result == 2
