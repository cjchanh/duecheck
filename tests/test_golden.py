"""Golden fixture replay tests for deterministic engine behavior."""

import json
from datetime import datetime, timezone
from pathlib import Path

from duecheck.cli import run_repair
from duecheck.delta import build_delta
from duecheck.ledger import build_ledger
from duecheck.risk import compute_overall_risk
from duecheck.types import AssignmentObservation, CourseInfo, serialize_payload

FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text())


def _load_expected(fixture_name: str, file_name: str) -> dict | list:
    return _load_json(FIXTURES_ROOT / fixture_name / file_name)


def _to_course_info(item: dict) -> CourseInfo:
    return CourseInfo(
        id=int(item["id"]),
        name=str(item["name"]),
        slug=str(item["slug"]),
        score=float(item["score"]) if item.get("score") is not None else None,
        grade=str(item["grade"]) if item.get("grade") is not None else None,
    )


def _to_observation(item: dict) -> AssignmentObservation:
    return AssignmentObservation(
        source_key=str(item.get("source_key") or "") or None,
        due_at=datetime.fromisoformat(str(item["due_at"]).replace("Z", "+00:00")),
        course=str(item["course"]),
        name=str(item["name"]),
    )


def _run_engine_fixture(fixture_name: str) -> tuple[list, dict, dict]:
    fixture_dir = FIXTURES_ROOT / fixture_name
    input_payload = _load_json(fixture_dir / "input.json")
    assert isinstance(input_payload, dict)

    courses = [_to_course_info(item) for item in input_payload["courses"]]
    previous_fixture = input_payload.get("previous_fixture")
    existing_ledger: dict[str, dict] = {}
    if isinstance(previous_fixture, str):
        previous_entries = _load_expected(previous_fixture, "expected_ledger.json")
        assert isinstance(previous_entries, list)
        existing_ledger = {str(item["item_id"]): item for item in previous_entries}

    pulled_at = str(input_payload["pulled_at"])
    now = datetime.fromisoformat(pulled_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    ledger = build_ledger(
        pulled_at,
        [_to_observation(item) for item in input_payload.get("due_48_items", [])],
        [_to_observation(item) for item in input_payload.get("due_7_items", [])],
        list(input_payload.get("missing_raw", [])),
        {course.id for course in courses},
        {course.id: course.name for course in courses},
        {course.name: course for course in courses},
        existing_ledger=existing_ledger or None,
        source_adapter="canvas",
    )
    delta = build_delta(existing_ledger, ledger, pulled_at, source_adapter="canvas")
    risk = compute_overall_risk(
        courses,
        list(input_payload.get("missing_raw", [])),
        now,
        source_adapter="canvas",
    )
    return serialize_payload(ledger), serialize_payload(delta), serialize_payload(risk)


def test_golden_001_first_run():
    ledger, delta, risk = _run_engine_fixture("golden_001")
    assert ledger == _load_expected("golden_001", "expected_ledger.json")
    assert delta == _load_expected("golden_001", "expected_delta.json")
    assert risk == _load_expected("golden_001", "expected_risk.json")


def test_golden_002_escalation_and_deadline():
    ledger, delta, risk = _run_engine_fixture("golden_002")
    assert ledger == _load_expected("golden_002", "expected_ledger.json")
    assert delta == _load_expected("golden_002", "expected_delta.json")
    assert risk == _load_expected("golden_002", "expected_risk.json")


def test_golden_003_repair_from_history(tmp_path: Path):
    input_payload = _load_json(FIXTURES_ROOT / "golden_003" / "input.json")
    assert isinstance(input_payload, dict)
    previous_fixture = str(input_payload["previous_fixture"])
    current_fixture = str(input_payload["current_fixture"])
    previous_pulled_at = str(input_payload["previous_pulled_at"])
    current_pulled_at = str(input_payload["current_pulled_at"])

    previous_run = tmp_path / "runs" / previous_pulled_at.replace(":", "-")
    previous_run.mkdir(parents=True)
    (previous_run / "ledger.json").write_text(json.dumps(_load_expected(previous_fixture, "expected_ledger.json")))
    (previous_run / "pulled_at.txt").write_text(previous_pulled_at + "\n")
    (tmp_path / "ledger.json").write_text(json.dumps(_load_expected(current_fixture, "expected_ledger.json")))
    (tmp_path / "risk.json").write_text(json.dumps(_load_expected(current_fixture, "expected_risk.json")))
    (tmp_path / "pulled_at.txt").write_text(current_pulled_at + "\n")

    result = run_repair(tmp_path)
    assert result["status"] == "repaired"
    assert _load_json(tmp_path / "ledger.json") == _load_expected("golden_003", "expected_ledger.json")
    assert _load_json(tmp_path / "delta.json") == _load_expected("golden_003", "expected_delta.json")
    assert _load_json(tmp_path / "risk.json") == _load_expected("golden_003", "expected_risk.json")


def test_threat_golden_fixture_deterministic():
    first = _run_engine_fixture("golden_002")
    second = _run_engine_fixture("golden_002")
    normalized_first = json.dumps(first, sort_keys=True)
    normalized_second = json.dumps(second, sort_keys=True)
    assert normalized_first == normalized_second
