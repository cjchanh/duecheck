"""Threat coverage for CLI UX surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from duecheck.cli import main, run_doctor, run_redact, run_verify
from duecheck.config import DuecheckConfig, save_config


def _write_summary_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "delta.json").write_text(json.dumps({"counts": {"escalated": 0}}))
    (out_dir / "risk.json").write_text(json.dumps({"overall": "LOW"}))


def test_threat_pull_env_overrides_config(tmp_path: Path, monkeypatch):
    config_root = tmp_path / "config"
    save_config(
        DuecheckConfig(
            canvas_url="https://config.example.com",
            canvas_token="config-token",
            out_dir=str(tmp_path / "config-output"),
        ),
        path=config_root / "duecheck" / "config.json",
        platform_name="posix",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("CANVAS_URL", "https://env.example.com")
    monkeypatch.setenv("CANVAS_TOKEN", "env-token")

    captured: dict[str, object] = {}

    def fake_run_pull(**kwargs):
        captured.update(kwargs)
        _write_summary_artifacts(kwargs["out_dir"])
        return {
            "courses": 1,
            "due_48h": 0,
            "due_7d": 0,
            "missing": 0,
            "risk_overall": "LOW",
        }

    monkeypatch.setattr("duecheck.cli.run_pull", fake_run_pull)

    result = main([])

    assert result == 0
    assert captured["canvas_url"] == "https://env.example.com"
    assert captured["token"] == "env-token"
    assert captured["out_dir"] == Path(tmp_path / "config-output").resolve()


def test_threat_pull_without_config_still_works(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "missing-config"))
    monkeypatch.delenv("CANVAS_URL", raising=False)
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)

    captured: dict[str, object] = {}

    def fake_run_pull(**kwargs):
        captured.update(kwargs)
        _write_summary_artifacts(kwargs["out_dir"])
        return {
            "courses": 1,
            "due_48h": 0,
            "due_7d": 0,
            "missing": 0,
            "risk_overall": "LOW",
        }

    monkeypatch.setattr("duecheck.cli.run_pull", fake_run_pull)

    result = main(
        [
            "--canvas-url",
            "https://canvas.example.com",
            "--canvas-token",
            "explicit-token",
            "--out-dir",
            str(tmp_path / "explicit-output"),
        ]
    )

    assert result == 0
    assert captured["canvas_url"] == "https://canvas.example.com"
    assert captured["token"] == "explicit-token"
    assert captured["out_dir"] == Path(tmp_path / "explicit-output").resolve()


def test_doctor_exit_code_all_clear(tmp_path: Path):
    from duecheck.cli import run_demo

    config_root = tmp_path / "config"
    run_demo(tmp_path)
    save_config(
        DuecheckConfig(
            canvas_url="https://canvas.example.com",
            token_env="CANVAS_TOKEN",
            out_dir=str(tmp_path),
        ),
        path=config_root / "duecheck" / "config.json",
        platform_name="posix",
    )

    _, exit_code = run_doctor(
        tmp_path,
        env={"XDG_CONFIG_HOME": str(config_root), "CANVAS_TOKEN": "demo-token"},
    )

    assert exit_code == 0


def test_doctor_exit_code_warnings_only(tmp_path: Path):
    _, exit_code = run_doctor(tmp_path, env={"XDG_CONFIG_HOME": str(tmp_path / "config")})
    assert exit_code == 1


def test_doctor_exit_code_blocking_failure(tmp_path: Path):
    from duecheck.cli import run_demo

    run_demo(tmp_path)
    risk = json.loads((tmp_path / "risk.json").read_text())
    risk["missing_count"] = "bad"
    (tmp_path / "risk.json").write_text(json.dumps(risk))

    _, exit_code = run_doctor(tmp_path, env={"XDG_CONFIG_HOME": str(tmp_path / "config")})
    assert exit_code == 2


def test_threat_doctor_flags_missing_token(tmp_path: Path):
    result, exit_code = run_doctor(tmp_path, env={"XDG_CONFIG_HOME": str(tmp_path / "config")})

    token_check = next(check for check in result["checks"] if check["name"] == "token")
    assert exit_code == 1
    assert token_check["status"] == "WARN"


def test_doctor_default_stays_local(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("duecheck.cli.CanvasAdapter", object())
    result, exit_code = run_doctor(tmp_path, env={"XDG_CONFIG_HOME": str(tmp_path / "config")})
    assert exit_code == 1
    assert all(check["name"] != "auth" for check in result["checks"])


def test_threat_doctor_reports_invalid_artifacts(tmp_path: Path):
    from duecheck.cli import run_demo

    run_demo(tmp_path)
    risk = json.loads((tmp_path / "risk.json").read_text())
    risk["missing_count"] = "bad"
    (tmp_path / "risk.json").write_text(json.dumps(risk))

    result, exit_code = run_doctor(tmp_path, env={"XDG_CONFIG_HOME": str(tmp_path / "config")})

    artifact_check = next(check for check in result["checks"] if check["name"] == "artifacts")
    assert exit_code == 2
    assert artifact_check["status"] == "FAIL"


def test_threat_redact_removes_real_names_and_source_keys(tmp_path: Path):
    from duecheck.cli import run_demo

    demo_dir = tmp_path / "demo"
    dest_dir = tmp_path / "redacted"
    run_demo(demo_dir)
    run_redact(demo_dir, dest_dir)

    combined = "\n".join(
        (dest_dir / name).read_text()
        for name in ("ledger.json", "delta.json", "risk.json", "changes.md", "report.html")
    )
    assert "English Composition" not in combined
    assert "Philosophy" not in combined
    assert "Quiz 5" not in combined
    assert "Reflection Paper 4" not in combined
    assert "canvas:" not in combined


def test_threat_redact_output_validates(tmp_path: Path):
    from duecheck.cli import run_demo

    demo_dir = tmp_path / "demo"
    dest_dir = tmp_path / "redacted"
    run_demo(demo_dir)
    run_redact(demo_dir, dest_dir)

    results, exit_code = run_verify(dest_dir)
    assert exit_code == 0
    assert results == {"ledger": [], "delta": [], "risk": []}


def test_threat_redact_is_deterministic(tmp_path: Path):
    from duecheck.cli import run_demo

    demo_dir = tmp_path / "demo"
    run_demo(demo_dir)
    dest_one = tmp_path / "redacted-one"
    dest_two = tmp_path / "redacted-two"

    run_redact(demo_dir, dest_one)
    run_redact(demo_dir, dest_two)

    for name in ("ledger.json", "delta.json", "risk.json", "changes.md", "report.html"):
        assert (dest_one / name).read_text() == (dest_two / name).read_text()


def test_threat_redact_bundle_includes_report_html(tmp_path: Path):
    from duecheck.cli import run_demo, run_report

    demo_dir = tmp_path / "demo"
    dest_dir = tmp_path / "redacted"
    run_demo(demo_dir)

    result = run_redact(demo_dir, dest_dir)
    report_result = run_report(dest_dir, html=True)

    assert (dest_dir / "report.html").exists()
    assert result["report_html"] == str(dest_dir / "report.html")
    assert report_result["status"] == "report_ready"
