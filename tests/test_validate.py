"""Tests for DueCheck artifact validation and fail-closed writes."""

import json
from pathlib import Path
from unittest.mock import patch

from duecheck import __version__
from duecheck.cli import main, run_demo
from duecheck.validate import validate_artifacts


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text())


def test_threat_artifact_missing_schema_version(tmp_path: Path):
    run_demo(tmp_path)
    ledger = _load_json(tmp_path / "ledger.json")
    delta = _load_json(tmp_path / "delta.json")
    risk = _load_json(tmp_path / "risk.json")

    assert ledger
    assert "schema_version" in ledger[0]
    assert delta["schema_version"] == "1.0"
    assert risk["schema_version"] == "1.0"


def test_threat_artifact_missing_engine_version(tmp_path: Path):
    run_demo(tmp_path)
    ledger = _load_json(tmp_path / "ledger.json")
    delta = _load_json(tmp_path / "delta.json")
    risk = _load_json(tmp_path / "risk.json")

    assert ledger[0]["engine_version"] == __version__
    assert delta["engine_version"] == __version__
    assert risk["engine_version"] == __version__


def test_threat_validate_rejects_corrupt_ledger(tmp_path: Path):
    run_demo(tmp_path)
    ledger = _load_json(tmp_path / "ledger.json")
    ledger[0]["name"] = ""
    (tmp_path / "ledger.json").write_text(json.dumps(ledger))

    results = validate_artifacts(tmp_path)
    assert results["ledger"]
    assert any("name" in error for error in results["ledger"])


def test_threat_validate_rejects_wrong_schema_version(tmp_path: Path):
    run_demo(tmp_path)
    delta = _load_json(tmp_path / "delta.json")
    delta["schema_version"] = "9.9"
    (tmp_path / "delta.json").write_text(json.dumps(delta))

    results = validate_artifacts(tmp_path)
    assert results["delta"]
    assert any("schema_version" in error for error in results["delta"])


def test_threat_verify_command_catches_invalid(tmp_path: Path):
    run_demo(tmp_path)
    risk = _load_json(tmp_path / "risk.json")
    risk["missing_count"] = "bad"
    (tmp_path / "risk.json").write_text(json.dumps(risk))

    result = main(["verify", "--out-dir", str(tmp_path), "--json"])
    assert result == 1


def test_threat_invalid_artifacts_do_not_overwrite_last_good_artifacts(tmp_path: Path):
    run_demo(tmp_path)
    before = {
        "ledger": (tmp_path / "ledger.json").read_text(),
        "delta": (tmp_path / "delta.json").read_text(),
        "risk": (tmp_path / "risk.json").read_text(),
        "changes": (tmp_path / "changes.md").read_text(),
    }

    with patch(
        "duecheck.cli.validate_payloads",
        return_value={"ledger": ["forced invalid"], "delta": [], "risk": []},
    ):
        try:
            run_demo(tmp_path)
        except RuntimeError as exc:
            assert "artifact validation failed" in str(exc)
        else:
            raise AssertionError("Expected run_demo to fail closed")

    assert (tmp_path / "ledger.json").read_text() == before["ledger"]
    assert (tmp_path / "delta.json").read_text() == before["delta"]
    assert (tmp_path / "risk.json").read_text() == before["risk"]
    assert (tmp_path / "changes.md").read_text() == before["changes"]


def test_threat_severity_label_rename_no_orphan_confidence(tmp_path: Path):
    run_demo(tmp_path)
    ledger_text = (tmp_path / "ledger.json").read_text()
    delta_text = (tmp_path / "delta.json").read_text()
    risk_text = (tmp_path / "risk.json").read_text()

    assert "\"severity_label\"" in ledger_text
    assert "\"severity_label\"" in delta_text
    assert "\"confidence\"" not in ledger_text
    assert "\"confidence\"" not in delta_text
    assert "\"confidence\"" not in risk_text
