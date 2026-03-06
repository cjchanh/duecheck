"""Local scheduling support for DueCheck."""

from __future__ import annotations

import os
import platform
import plistlib
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .config import config_path, resolve_runtime_settings

DEFAULT_SCHEDULE_LABEL = "io.duecheck.sync"
DEFAULT_SCHEDULE_HOUR = 7
DEFAULT_SCHEDULE_MINUTE = 0
SCHEDULE_TOKEN_ENV = "DUECHECK_SCHEDULE_TOKEN"


@dataclass(frozen=True)
class SchedulePaths:
    plist_path: Path
    script_path: Path
    stdout_path: Path
    stderr_path: Path


def _home_dir(env: Mapping[str, str] | None = None) -> Path:
    env_map = os.environ if env is None else env
    home = env_map.get("HOME")
    if home:
        return Path(home).expanduser()
    return Path.home()


def schedule_paths(
    *,
    env: Mapping[str, str] | None = None,
    label: str = DEFAULT_SCHEDULE_LABEL,
) -> SchedulePaths:
    home = _home_dir(env)
    config_root = config_path(env).parent
    return SchedulePaths(
        plist_path=home / "Library" / "LaunchAgents" / f"{label}.plist",
        script_path=config_root / "run-scheduled-sync.sh",
        stdout_path=home / "Library" / "Logs" / "DueCheck" / "schedule.log",
        stderr_path=home / "Library" / "Logs" / "DueCheck" / "schedule.err.log",
    )


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temp_name = handle.name
        Path(temp_name).replace(path)
    finally:
        if temp_name is not None:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        return


def _quote_command(args: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in args)


def render_schedule_script(
    *,
    python_executable: str,
    canvas_url: str,
    out_dir: str,
    grade_threshold: float,
    course_filter: list[str] | None,
    config_env: Mapping[str, str] | None,
    embedded_token: str,
) -> str:
    pull_args = [
        python_executable,
        "-m",
        "duecheck.cli",
        "--canvas-url",
        canvas_url,
        "--out-dir",
        out_dir,
        "--grade-threshold",
        str(grade_threshold),
    ]
    if course_filter:
        pull_args.append("--course-filter")
        pull_args.extend(course_filter)
    if embedded_token:
        pull_args.extend(["--token-env", SCHEDULE_TOKEN_ENV])

    report_args = [
        python_executable,
        "-m",
        "duecheck.cli",
        "report",
        "--html",
        "--out-dir",
        out_dir,
    ]

    lines = [
        "#!/bin/sh",
        "set -eu",
    ]
    xdg_config_home = ""
    if config_env is not None:
        xdg_config_home = str(config_env.get("XDG_CONFIG_HOME") or "")
    if xdg_config_home:
        lines.append(f"export XDG_CONFIG_HOME={shlex.quote(xdg_config_home)}")
    if embedded_token:
        lines.append(f"export {SCHEDULE_TOKEN_ENV}={shlex.quote(embedded_token)}")
    lines.append(_quote_command(pull_args))
    lines.append(_quote_command(report_args))
    lines.append("")
    return "\n".join(lines)


def render_launch_agent(
    *,
    label: str,
    script_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    hour: int,
    minute: int,
) -> bytes:
    payload = {
        "Label": label,
        "ProgramArguments": [str(script_path)],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "RunAtLoad": False,
        "ProcessType": "Background",
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def _launchctl_domain(uid: int) -> str:
    return f"gui/{uid}"


def _run_launchctl(
    args: list[str],
    *,
    subprocess_run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> subprocess.CompletedProcess:
    return subprocess_run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )


def install_schedule(
    *,
    hour: int = DEFAULT_SCHEDULE_HOUR,
    minute: int = DEFAULT_SCHEDULE_MINUTE,
    canvas_url: str | None = None,
    canvas_token: str | None = None,
    token_env: str | None = None,
    out_dir: str | None = None,
    course_filter: list[str] | None = None,
    grade_threshold: float | None = None,
    env: Mapping[str, str] | None = None,
    platform_system: str | None = None,
    subprocess_run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    python_executable: str | None = None,
    uid: int | None = None,
    label: str = DEFAULT_SCHEDULE_LABEL,
) -> dict:
    target_platform = platform_system or platform.system()
    if target_platform != "Darwin":
        raise RuntimeError("Scheduling is currently supported on macOS only.")

    env_map = os.environ if env is None else dict(env)
    settings = resolve_runtime_settings(
        canvas_url=canvas_url,
        canvas_token=canvas_token,
        token_env=token_env,
        out_dir=out_dir,
        course_filter=course_filter,
        grade_threshold=grade_threshold,
        env=env_map,
    )
    if not settings.canvas_url:
        raise RuntimeError("Canvas URL not resolved. Run 'duecheck init' or pass --canvas-url.")
    if not settings.token:
        raise RuntimeError(
            "Canvas token not resolved. Run 'duecheck init', set CANVAS_TOKEN, or pass --canvas-token."
        )

    paths = schedule_paths(env=env_map, label=label)
    script_token = ""
    token_storage = "config"
    if not (settings.config and settings.config.canvas_token):
        script_token = settings.token
        token_storage = "schedule_script"

    script = render_schedule_script(
        python_executable=python_executable or os.sys.executable,
        canvas_url=settings.canvas_url,
        out_dir=settings.out_dir,
        grade_threshold=settings.grade_threshold,
        course_filter=settings.course_filter,
        config_env=env_map,
        embedded_token=script_token,
    )
    plist_bytes = render_launch_agent(
        label=label,
        script_path=paths.script_path,
        stdout_path=paths.stdout_path,
        stderr_path=paths.stderr_path,
        hour=hour,
        minute=minute,
    )

    _atomic_write_text(paths.script_path, script)
    _chmod_best_effort(paths.script_path, 0o700)
    paths.stdout_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes(paths.plist_path, plist_bytes)
    _chmod_best_effort(paths.plist_path, 0o600)

    resolved_uid = os.getuid() if uid is None else uid
    domain = _launchctl_domain(resolved_uid)
    _run_launchctl(["launchctl", "bootout", domain, str(paths.plist_path)], subprocess_run=subprocess_run)
    bootstrap_result = _run_launchctl(
        ["launchctl", "bootstrap", domain, str(paths.plist_path)],
        subprocess_run=subprocess_run,
    )
    if bootstrap_result.returncode != 0:
        detail = (bootstrap_result.stderr or bootstrap_result.stdout or "").strip()
        raise RuntimeError(f"Failed to install LaunchAgent: {detail or bootstrap_result.returncode}")

    return {
        "status": "installed",
        "platform": target_platform,
        "label": label,
        "plist_path": str(paths.plist_path),
        "script_path": str(paths.script_path),
        "stdout_path": str(paths.stdout_path),
        "stderr_path": str(paths.stderr_path),
        "hour": hour,
        "minute": minute,
        "out_dir": settings.out_dir,
        "token_storage": token_storage,
    }


def schedule_status(
    *,
    env: Mapping[str, str] | None = None,
    platform_system: str | None = None,
    subprocess_run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    uid: int | None = None,
    label: str = DEFAULT_SCHEDULE_LABEL,
) -> dict:
    target_platform = platform_system or platform.system()
    paths = schedule_paths(env=env, label=label)
    if target_platform != "Darwin":
        return {
            "status": "unsupported",
            "platform": target_platform,
            "detail": "Scheduling is currently supported on macOS only.",
        }
    if not paths.plist_path.exists():
        return {
            "status": "absent",
            "platform": target_platform,
            "label": label,
            "plist_path": str(paths.plist_path),
        }

    payload = plistlib.loads(paths.plist_path.read_bytes())
    start = payload.get("StartCalendarInterval", {})
    resolved_uid = os.getuid() if uid is None else uid
    domain = _launchctl_domain(resolved_uid)
    loaded_result = _run_launchctl(
        ["launchctl", "print", f"{domain}/{label}"],
        subprocess_run=subprocess_run,
    )
    return {
        "status": "installed",
        "platform": target_platform,
        "label": label,
        "plist_path": str(paths.plist_path),
        "script_path": str(paths.script_path),
        "stdout_path": str(paths.stdout_path),
        "stderr_path": str(paths.stderr_path),
        "hour": int(start.get("Hour", DEFAULT_SCHEDULE_HOUR)),
        "minute": int(start.get("Minute", DEFAULT_SCHEDULE_MINUTE)),
        "loaded": loaded_result.returncode == 0,
    }


def remove_schedule(
    *,
    env: Mapping[str, str] | None = None,
    platform_system: str | None = None,
    subprocess_run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    uid: int | None = None,
    label: str = DEFAULT_SCHEDULE_LABEL,
) -> dict:
    target_platform = platform_system or platform.system()
    if target_platform != "Darwin":
        raise RuntimeError("Scheduling is currently supported on macOS only.")

    paths = schedule_paths(env=env, label=label)
    if not paths.plist_path.exists() and not paths.script_path.exists():
        return {
            "status": "absent",
            "label": label,
            "plist_path": str(paths.plist_path),
            "script_path": str(paths.script_path),
        }

    resolved_uid = os.getuid() if uid is None else uid
    domain = _launchctl_domain(resolved_uid)
    _run_launchctl(["launchctl", "bootout", domain, str(paths.plist_path)], subprocess_run=subprocess_run)

    removed: list[str] = []
    for path in (paths.plist_path, paths.script_path):
        if path.exists():
            path.unlink()
            removed.append(str(path))

    return {
        "status": "removed",
        "label": label,
        "removed": removed,
    }
