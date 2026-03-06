"""Threat coverage for local scheduling support."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

import pytest

from duecheck.config import DuecheckConfig, save_config
from duecheck.schedule import (
    install_schedule,
    remove_schedule,
    schedule_paths,
    schedule_status,
)


def _fake_launchctl(*, print_returncode: int = 0):
    calls: list[list[str]] = []

    def _run(args, check=False, capture_output=False, text=False):
        del check, capture_output, text
        command = [str(part) for part in args]
        calls.append(command)
        if command[:2] == ["launchctl", "print"]:
            return subprocess.CompletedProcess(command, print_returncode, stdout="", stderr="")
        if command[:2] == ["launchctl", "bootstrap"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["launchctl", "bootout"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return calls, _run


def test_schedule_install_writes_launch_agent(tmp_path: Path):
    home = tmp_path / "home"
    config_root = home / ".config"
    save_config(
        DuecheckConfig(
            canvas_url="https://canvas.example.com",
            canvas_token="config-token",
            out_dir=str(tmp_path / "classes"),
            grade_threshold=82.5,
        ),
        path=config_root / "duecheck" / "config.json",
        platform_name="posix",
    )
    calls, fake_run = _fake_launchctl()

    result = install_schedule(
        env={"HOME": str(home)},
        platform_system="Darwin",
        subprocess_run=fake_run,
        python_executable="/usr/bin/python3",
        uid=501,
    )

    paths = schedule_paths(env={"HOME": str(home)})
    assert result["status"] == "installed"
    assert result["token_storage"] == "config"
    assert paths.plist_path.exists()
    assert paths.script_path.exists()

    script = paths.script_path.read_text()
    assert "python3 -m duecheck.cli --canvas-url https://canvas.example.com" in script
    assert "--out-dir" in script
    assert "report --html" in script
    assert "DUECHECK_SCHEDULE_TOKEN" not in script

    payload = plistlib.loads(paths.plist_path.read_bytes())
    assert payload["Label"] == result["label"]
    assert payload["StartCalendarInterval"] == {"Hour": 7, "Minute": 0}
    assert payload["ProgramArguments"] == [str(paths.script_path)]

    assert ["launchctl", "bootout", "gui/501", str(paths.plist_path)] in calls
    assert ["launchctl", "bootstrap", "gui/501", str(paths.plist_path)] in calls


def test_schedule_install_embeds_env_token_when_needed(tmp_path: Path):
    home = tmp_path / "home"
    calls, fake_run = _fake_launchctl()

    result = install_schedule(
        canvas_url="https://canvas.example.com",
        out_dir=str(tmp_path / "classes"),
        env={"HOME": str(home), "CANVAS_TOKEN": "env-token"},
        platform_system="Darwin",
        subprocess_run=fake_run,
        python_executable="/usr/bin/python3",
        uid=501,
    )

    del calls
    paths = schedule_paths(env={"HOME": str(home)})
    script = paths.script_path.read_text()
    assert result["token_storage"] == "schedule_script"
    assert "export DUECHECK_SCHEDULE_TOKEN=env-token" in script
    assert "--token-env DUECHECK_SCHEDULE_TOKEN" in script


def test_schedule_status_reports_installed(tmp_path: Path):
    home = tmp_path / "home"
    config_root = home / ".config"
    save_config(
        DuecheckConfig(
            canvas_url="https://canvas.example.com",
            canvas_token="config-token",
            out_dir=str(tmp_path / "classes"),
        ),
        path=config_root / "duecheck" / "config.json",
        platform_name="posix",
    )
    calls, fake_run = _fake_launchctl(print_returncode=0)
    install_schedule(
        env={"HOME": str(home)},
        platform_system="Darwin",
        subprocess_run=fake_run,
        python_executable="/usr/bin/python3",
        uid=501,
    )

    result = schedule_status(
        env={"HOME": str(home)},
        platform_system="Darwin",
        subprocess_run=fake_run,
        uid=501,
    )

    assert result["status"] == "installed"
    assert result["loaded"] is True
    assert ["launchctl", "print", "gui/501/io.duecheck.sync"] in calls


def test_schedule_remove_cleans_files(tmp_path: Path):
    home = tmp_path / "home"
    config_root = home / ".config"
    save_config(
        DuecheckConfig(
            canvas_url="https://canvas.example.com",
            canvas_token="config-token",
            out_dir=str(tmp_path / "classes"),
        ),
        path=config_root / "duecheck" / "config.json",
        platform_name="posix",
    )
    calls, fake_run = _fake_launchctl()
    install_schedule(
        env={"HOME": str(home)},
        platform_system="Darwin",
        subprocess_run=fake_run,
        python_executable="/usr/bin/python3",
        uid=501,
    )
    paths = schedule_paths(env={"HOME": str(home)})

    result = remove_schedule(
        env={"HOME": str(home)},
        platform_system="Darwin",
        subprocess_run=fake_run,
        uid=501,
    )

    assert result["status"] == "removed"
    assert not paths.plist_path.exists()
    assert not paths.script_path.exists()
    assert ["launchctl", "bootout", "gui/501", str(paths.plist_path)] in calls


def test_schedule_install_rejects_unsupported_platform(tmp_path: Path):
    with pytest.raises(RuntimeError, match="macOS only"):
        install_schedule(
            canvas_url="https://canvas.example.com",
            canvas_token="token",
            out_dir=str(tmp_path / "classes"),
            env={"HOME": str(tmp_path / "home")},
            platform_system="Linux",
        )
