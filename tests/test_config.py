"""Tests for DueCheck config and init flow."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from duecheck.cli import main, run_init
from duecheck.config import DuecheckConfig, config_path, load_config, save_config


def test_threat_init_creates_private_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    result = main(
        [
            "init",
            "--canvas-url",
            "https://canvas.example.com",
            "--canvas-token",
            "secret-token",
            "--out-dir",
            str(tmp_path / "output"),
            "--yes",
        ]
    )

    assert result == 0
    path = config_path()
    payload = json.loads(path.read_text())
    assert payload["canvas_url"] == "https://canvas.example.com"
    assert payload["canvas_token"] == "secret-token"
    assert payload["out_dir"] == str(tmp_path / "output")
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_threat_init_does_not_echo_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    token = "super-secret-token"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    result = main(
        [
            "init",
            "--canvas-url",
            "https://canvas.example.com",
            "--canvas-token",
            token,
            "--out-dir",
            str(tmp_path / "output"),
            "--yes",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert token not in captured.out
    assert token not in captured.err


def test_threat_init_fails_without_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr("duecheck.cli._stdin_is_tty", lambda: False)

    result = main(
        [
            "init",
            "--canvas-url",
            "https://canvas.example.com",
            "--token-env",
            "ALT_TOKEN",
            "--out-dir",
            str(tmp_path / "output"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "--yes" in captured.err


def test_threat_init_warns_when_posix_permissions_unavailable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    run_init(
        canvas_url="https://canvas.example.com",
        canvas_token=None,
        token_env="CANVAS_TOKEN",
        out_dir=str(tmp_path / "output"),
        grade_threshold=None,
        yes=True,
        print_path=False,
        env={"XDG_CONFIG_HOME": str(tmp_path / "config")},
        stdin_is_tty=False,
        platform_name="nt",
    )

    captured = capsys.readouterr()
    assert "WARN:" in captured.err
    assert "permissions not hardened" in captured.err


def test_load_config_round_trip(tmp_path: Path):
    path = tmp_path / "config" / "config.json"
    save_config(
        DuecheckConfig(
            canvas_url="https://canvas.example.com",
            canvas_token="secret-token",
            out_dir="/tmp/duecheck-output",
            course_filter=["English", "Philosophy"],
            grade_threshold=77.5,
            token_env="ALT_TOKEN",
        ),
        path=path,
        platform_name="posix",
    )

    loaded = load_config(path)
    assert loaded is not None
    assert loaded.canvas_url == "https://canvas.example.com"
    assert loaded.canvas_token == "secret-token"
    assert loaded.out_dir == "/tmp/duecheck-output"
    assert loaded.course_filter == ["English", "Philosophy"]
    assert loaded.grade_threshold == 77.5
    assert loaded.token_env == "ALT_TOKEN"
