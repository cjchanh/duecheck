"""Schema and validator coverage for golden fixtures and demo output."""

import json
from pathlib import Path

from duecheck.cli import run_demo
from duecheck.validate import validate_artifacts, validate_payloads

FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text())


def test_golden_expected_outputs_validate():
    for fixture_name in ("golden_001", "golden_002", "golden_003"):
        ledger = _load_json(FIXTURES_ROOT / fixture_name / "expected_ledger.json")
        delta = _load_json(FIXTURES_ROOT / fixture_name / "expected_delta.json")
        risk = _load_json(FIXTURES_ROOT / fixture_name / "expected_risk.json")
        assert validate_payloads(ledger, delta, risk) == {
            "ledger": [],
            "delta": [],
            "risk": [],
        }


def test_demo_output_validates(tmp_path: Path):
    run_demo(tmp_path)
    assert validate_artifacts(tmp_path) == {
        "ledger": [],
        "delta": [],
        "risk": [],
    }
