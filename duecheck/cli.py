"""DueCheck CLI — pull Canvas data and compute academic risk."""

from __future__ import annotations

import argparse
import getpass
import importlib.resources as resources
import json
import os
import sys
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .adapter import CanvasAdapter
from .config import DEFAULT_TOKEN_ENV, DuecheckConfig, config_path, resolve_runtime_settings, save_config
from .delta import build_delta, render_delta_markdown
from .ledger import build_ledger, load_existing_ledger, resolve_repair_pulled_ts
from .redact import build_redacted_bundle
from .report import write_report_html
from .risk import compute_overall_risk
from .schedule import (
    DEFAULT_SCHEDULE_HOUR,
    DEFAULT_SCHEDULE_MINUTE,
    install_schedule,
    remove_schedule,
    schedule_status,
)
from .types import delta_report_from_mapping, ledger_entry_from_mapping, risk_report_from_mapping, serialize_payload
from .validate import validate_artifacts, validate_payloads

ARTIFACT_JSON_FILES = ("ledger.json", "delta.json", "risk.json")
ARTIFACT_TEXT_FILES = ("changes.md", "pulled_at.txt")


def _json_text(payload: dict | list) -> str:
    return json.dumps(serialize_payload(payload), indent=2) + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
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


def _write_json(path: Path, payload: dict | list) -> None:
    _atomic_write_text(path, _json_text(payload))


def _run_dir(out_dir: Path, pulled_ts: str) -> Path:
    return out_dir / "runs" / pulled_ts.replace(":", "-")


def _snapshot_existing_run(out_dir: Path) -> None:
    pulled_at_path = out_dir / "pulled_at.txt"
    ledger_path = out_dir / "ledger.json"
    if not pulled_at_path.exists() or not ledger_path.exists():
        return

    pulled_ts = pulled_at_path.read_text(errors="ignore").strip()
    if not pulled_ts:
        return

    run_dir = _run_dir(out_dir, pulled_ts)
    if (run_dir / "ledger.json").exists():
        return

    run_dir.mkdir(parents=True, exist_ok=True)
    for file_name in ARTIFACT_JSON_FILES + ARTIFACT_TEXT_FILES:
        source = out_dir / file_name
        if source.exists():
            _atomic_write_text(run_dir / file_name, source.read_text(errors="ignore"))


def _validate_payload_bundle(ledger: list, delta: dict, risk: dict) -> None:
    results = validate_payloads(ledger, delta, risk)
    failures = {name: errors for name, errors in results.items() if errors}
    if not failures:
        return

    lines = ["artifact validation failed"]
    for name, errors in failures.items():
        for error in errors:
            lines.append(f"{name}: {error}")
    raise RuntimeError("; ".join(lines))


def _write_artifact_bundle(
    target_dir: Path,
    *,
    pulled_ts: str,
    ledger: list[dict],
    delta: dict,
    changes_md: str,
    risk: dict,
) -> None:
    _write_json(target_dir / "ledger.json", ledger)
    _write_json(target_dir / "delta.json", delta)
    _atomic_write_text(target_dir / "changes.md", changes_md)
    _write_json(target_dir / "risk.json", risk)
    _atomic_write_text(target_dir / "pulled_at.txt", pulled_ts + "\n")


def _write_pull_artifacts(
    out_dir: Path,
    *,
    pulled_ts: str,
    ledger: list,
    delta: object,
    changes_md: str,
    risk: object,
) -> None:
    ledger_payload = serialize_payload(ledger)
    delta_payload = serialize_payload(delta)
    risk_payload = serialize_payload(risk)
    _validate_payload_bundle(ledger_payload, delta_payload, risk_payload)

    out_dir.mkdir(parents=True, exist_ok=True)
    _snapshot_existing_run(out_dir)
    _write_artifact_bundle(
        out_dir,
        pulled_ts=pulled_ts,
        ledger=ledger_payload,
        delta=delta_payload,
        changes_md=changes_md,
        risk=risk_payload,
    )

    run_dir = _run_dir(out_dir, pulled_ts)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_artifact_bundle(
        run_dir,
        pulled_ts=pulled_ts,
        ledger=ledger_payload,
        delta=delta_payload,
        changes_md=changes_md,
        risk=risk_payload,
    )


def _open_report_in_browser(report_path: Path) -> bool:
    if not report_path.exists():
        print(f"WARN: report unavailable at {report_path}; --open skipped", file=sys.stderr)
        return False
    try:
        return bool(webbrowser.open(report_path.resolve().as_uri()))
    except webbrowser.Error as exc:
        print(f"WARN: failed to open browser for {report_path}: {exc}", file=sys.stderr)
        return False


def _stdin_is_tty() -> bool:
    isatty = getattr(sys.stdin, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _prompt_text(prompt: str, *, default: str | None = None, input_fn: Callable[[str], str] = input) -> str:
    rendered_prompt = prompt if default is None else f"{prompt}"
    value = input_fn(rendered_prompt).strip()
    if value:
        return value
    return default or ""


def _prompt_yes_no(prompt: str, *, default: bool = False, input_fn: Callable[[str], str] = input) -> bool:
    value = input_fn(prompt).strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _packaged_asset_paths() -> dict[str, Path]:
    package_root = resources.files("duecheck")
    return {
        "demo_bundle": Path(str(package_root.joinpath("demo_data", "sample_bundle.json"))),
        "ledger_schema": Path(str(package_root.joinpath("schemas", "ledger.schema.json"))),
        "delta_schema": Path(str(package_root.joinpath("schemas", "delta.schema.json"))),
        "risk_schema": Path(str(package_root.joinpath("schemas", "risk.schema.json"))),
    }


def _doctor_probe_directory(out_dir: Path) -> tuple[str, str]:
    if out_dir.exists():
        if not out_dir.is_dir():
            return ("FAIL", f"{out_dir} exists but is not a directory")
        try:
            with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".duecheck-doctor-", delete=True):
                pass
        except OSError as exc:
            return ("FAIL", f"{out_dir} is not writable: {exc}")
        return ("PASS", f"{out_dir} exists and is writable")

    probe_parent = out_dir.parent
    while not probe_parent.exists() and probe_parent != probe_parent.parent:
        probe_parent = probe_parent.parent
    if not probe_parent.exists():
        return ("FAIL", f"{out_dir} is not creatable: no writable parent found")
    try:
        with tempfile.NamedTemporaryFile(dir=probe_parent, prefix=".duecheck-doctor-", delete=True):
            pass
    except OSError as exc:
        return ("FAIL", f"{out_dir} is not creatable from {probe_parent}: {exc}")
    return ("PASS", f"{out_dir} does not exist yet but is creatable from {probe_parent}")


def _doctor_artifact_status(out_dir: Path) -> tuple[str, str]:
    artifact_paths = [out_dir / name for name in ARTIFACT_JSON_FILES]
    existing = [path.exists() for path in artifact_paths]
    if not any(existing):
        return ("WARN", f"No artifacts found in {out_dir}")
    if not all(existing):
        missing = [path.name for path in artifact_paths if not path.exists()]
        return ("FAIL", f"Incomplete artifact bundle: missing {', '.join(missing)}")
    try:
        results = validate_artifacts(out_dir)
    except Exception as exc:
        return ("FAIL", str(exc))
    failures = {name: errors for name, errors in results.items() if errors}
    if failures:
        summary = ", ".join(f"{name}={len(errors)}" for name, errors in failures.items())
        return ("FAIL", f"Artifact validation failed ({summary})")
    return ("PASS", f"Artifacts validate in {out_dir}")


def _doctor_packaged_assets_status() -> tuple[str, str]:
    try:
        assets = _packaged_asset_paths()
    except Exception as exc:  # pragma: no cover - importlib.resources failure is environment-specific
        return ("FAIL", f"Failed to resolve packaged assets: {exc}")
    missing = [label for label, path in assets.items() if not path.is_file()]
    if missing:
        return ("FAIL", f"Missing packaged assets: {', '.join(missing)}")
    return ("PASS", "Packaged demo bundle and schemas are accessible")


def _doctor_exit_code(checks: list[dict[str, str]]) -> int:
    statuses = {check["status"] for check in checks}
    if "FAIL" in statuses:
        return 2
    if "WARN" in statuses:
        return 1
    return 0


def _available_run_snapshots(out_dir: Path) -> list[tuple[str, Path]]:
    runs_dir = out_dir / "runs"
    if not runs_dir.exists():
        return []

    snapshots: list[tuple[str, Path]] = []
    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue
        pulled_at_path = child / "pulled_at.txt"
        ledger_path = child / "ledger.json"
        if not pulled_at_path.exists() or not ledger_path.exists():
            continue
        pulled_ts = pulled_at_path.read_text(errors="ignore").strip()
        if pulled_ts:
            snapshots.append((pulled_ts, child))
    return sorted(snapshots, key=lambda item: item[0])


def _load_previous_run_ledger(out_dir: Path, pulled_ts: str) -> tuple[str | None, dict[str, dict] | None]:
    for previous_pulled_ts, run_dir in reversed(_available_run_snapshots(out_dir)):
        if previous_pulled_ts >= pulled_ts:
            continue
        return previous_pulled_ts, load_existing_ledger(run_dir / "ledger.json")
    return (None, None)


def _load_demo_bundle() -> dict:
    demo_path = resources.files("duecheck").joinpath("demo_data", "sample_bundle.json")
    try:
        payload = json.loads(demo_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Failed to load packaged demo bundle") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected demo bundle shape")
    return payload


def parse_pull_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck",
        description="Canvas early warning engine — pull assignments and compute risk.",
        epilog=(
            "Extra commands: 'duecheck init', 'duecheck demo --out-dir DIR', "
            "'duecheck doctor --out-dir DIR', 'duecheck redact --out-dir DIR --dest DIR', "
            "'duecheck report --html --out-dir DIR', 'duecheck schedule ...', "
            "and 'duecheck verify --out-dir DIR'."
        ),
    )
    parser.add_argument(
        "--canvas-url",
        default=None,
        help="Canvas base URL (or set CANVAS_URL env var)",
    )
    parser.add_argument(
        "--token-env",
        default=None,
        help="Environment variable name containing Canvas API token",
    )
    parser.add_argument(
        "--canvas-token",
        default=None,
        help="Canvas API token to use directly for this run",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for ledger, delta, and risk files",
    )
    parser.add_argument(
        "--course-filter",
        nargs="*",
        default=None,
        help="Course name substrings to filter (e.g. 'CS 101' 'MATH 200')",
    )
    parser.add_argument(
        "--grade-threshold",
        type=float,
        default=None,
        help="Grade threshold for risk scoring (default: 80.0)",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Rebuild delta and changes from existing ledger",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output summary as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--fail-on",
        default="",
        help="Exit 2 when a risk or delta threshold is breached (HIGH, MEDIUM, escalated, missing).",
    )
    return parser.parse_args(argv)


def parse_init_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck init",
        description="Create a local DueCheck config with CLI defaults.",
    )
    parser.add_argument("--canvas-url", default=None, help="Default Canvas base URL")
    parser.add_argument("--canvas-token", default=None, help="Canvas API token to optionally store in config")
    parser.add_argument("--token-env", default=None, help="Environment variable name to read the Canvas token from")
    parser.add_argument("--out-dir", default=None, help="Default output directory")
    parser.add_argument(
        "--grade-threshold",
        type=float,
        default=None,
        help="Default risk threshold to save in config",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Run non-interactively; all required values must be provided as flags",
    )
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="Print the config path and exit",
    )
    return parser.parse_args(argv)


def parse_demo_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck demo",
        description="Write a packaged demo dataset to an output directory.",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Output directory for demo artifacts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output summary as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the generated report in your default browser",
    )
    return parser.parse_args(argv)


def parse_doctor_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck doctor",
        description="Run local diagnostics for config, artifacts, and packaged assets.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to inspect for DueCheck artifacts",
    )
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Run a lightweight Canvas auth check using the resolved URL and token",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output diagnostics as JSON",
    )
    return parser.parse_args(argv)


def parse_report_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck report",
        description="Render a local report from existing DueCheck artifacts.",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Directory containing ledger, delta, risk, and timestamp artifacts",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Write a self-contained HTML report",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output file path (defaults to OUT_DIR/report.html)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output summary as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the generated HTML report in your default browser",
    )
    return parser.parse_args(argv)


def parse_redact_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck redact",
        description="Write a redacted bug-report bundle from an existing output directory.",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Source directory containing DueCheck artifacts",
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Destination directory for the redacted bundle",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output summary as JSON",
    )
    return parser.parse_args(argv)


def parse_verify_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck verify",
        description="Validate DueCheck artifacts in an output directory.",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Directory containing ledger, delta, and risk artifacts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output validation results as JSON",
    )
    return parser.parse_args(argv)


def parse_schedule_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck schedule",
        description="Install or inspect a local DueCheck sync schedule (macOS-first).",
    )
    subparsers = parser.add_subparsers(dest="schedule_command", required=True)

    install_parser = subparsers.add_parser(
        "install",
        help="Install a macOS LaunchAgent that runs DueCheck daily and refreshes the HTML report.",
    )
    install_parser.add_argument("--hour", type=int, choices=range(24), default=DEFAULT_SCHEDULE_HOUR)
    install_parser.add_argument("--minute", type=int, choices=range(60), default=DEFAULT_SCHEDULE_MINUTE)
    install_parser.add_argument("--canvas-url", default=None, help="Canvas base URL override for the scheduled job")
    install_parser.add_argument(
        "--token-env",
        default=None,
        help="Environment variable name containing the Canvas token for schedule install",
    )
    install_parser.add_argument(
        "--canvas-token",
        default=None,
        help="Canvas token to resolve during schedule install",
    )
    install_parser.add_argument("--out-dir", default=None, help="Output directory override for the scheduled job")
    install_parser.add_argument(
        "--course-filter",
        nargs="*",
        default=None,
        help="Course name substrings to filter in the scheduled job",
    )
    install_parser.add_argument(
        "--grade-threshold",
        type=float,
        default=None,
        help="Risk threshold override for the scheduled job",
    )
    install_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output schedule details as JSON",
    )

    status_parser = subparsers.add_parser("status", help="Show the current schedule status.")
    status_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output schedule details as JSON",
    )

    remove_parser = subparsers.add_parser("remove", help="Remove the current macOS LaunchAgent schedule.")
    remove_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output schedule details as JSON",
    )

    return parser.parse_args(argv)


def run_init(
    *,
    canvas_url: str | None,
    canvas_token: str | None,
    token_env: str | None,
    out_dir: str | None,
    grade_threshold: float | None,
    yes: bool,
    print_path: bool,
    env: dict[str, str] | None = None,
    stdin_is_tty: bool | None = None,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    platform_name: str | None = None,
) -> dict:
    env_map = os.environ.copy() if env is None else dict(env)
    resolved_config_path = config_path(env_map)
    if print_path:
        return {"status": "config_path", "config_path": str(resolved_config_path)}

    is_tty = _stdin_is_tty() if stdin_is_tty is None else stdin_is_tty
    if not is_tty and not yes:
        raise RuntimeError("Non-interactive init requires --yes plus explicit flags.")

    if yes:
        missing: list[str] = []
        if not canvas_url or not canvas_url.strip():
            missing.append("--canvas-url")
        if not out_dir or not out_dir.strip():
            missing.append("--out-dir")
        if not (token_env and token_env.strip()) and not (canvas_token and canvas_token.strip()):
            missing.append("--token-env or --canvas-token")
        if missing:
            raise RuntimeError(
                "Non-interactive init requires --yes plus explicit flags: " + ", ".join(missing)
            )
        resolved_canvas_url = canvas_url.strip()
        resolved_out_dir = out_dir.strip()
        resolved_token_env = (token_env or "").strip()
        stored_token = (canvas_token or "").strip()
        resolved_grade_threshold = float(grade_threshold) if grade_threshold is not None else None
    else:
        resolved_canvas_url = canvas_url.strip() if canvas_url else _prompt_text("Canvas URL: ", input_fn=input_fn)
        if not resolved_canvas_url:
            raise RuntimeError("Canvas URL is required")

        stored_token = ""
        resolved_token_env = (token_env or "").strip()
        direct_token = (canvas_token or "").strip()
        if direct_token:
            if _prompt_yes_no("Store token in config as plaintext? [y/N]: ", input_fn=input_fn):
                stored_token = direct_token
            else:
                resolved_token_env = resolved_token_env or _prompt_text(
                    "Token env name [CANVAS_TOKEN]: ",
                    default=DEFAULT_TOKEN_ENV,
                    input_fn=input_fn,
                )
        elif resolved_token_env:
            pass
        else:
            token_mode = _prompt_text(
                "Token source [env/token]: ",
                default="env",
                input_fn=input_fn,
            ).lower()
            if token_mode.startswith("t"):
                entered_token = getpass_fn("Canvas token (input hidden): ").strip()
                if not entered_token:
                    raise RuntimeError("Canvas token is required")
                if _prompt_yes_no("Store token in config as plaintext? [y/N]: ", input_fn=input_fn):
                    stored_token = entered_token
                else:
                    resolved_token_env = _prompt_text(
                        "Token env name [CANVAS_TOKEN]: ",
                        default=DEFAULT_TOKEN_ENV,
                        input_fn=input_fn,
                    )
            else:
                resolved_token_env = _prompt_text(
                    "Token env name [CANVAS_TOKEN]: ",
                    default=DEFAULT_TOKEN_ENV,
                    input_fn=input_fn,
                )

        if not stored_token and not resolved_token_env:
            resolved_token_env = DEFAULT_TOKEN_ENV

        resolved_out_dir = out_dir.strip() if out_dir else _prompt_text(
            "Default out_dir [.]: ",
            default=".",
            input_fn=input_fn,
        )
        if not resolved_out_dir:
            raise RuntimeError("Default out_dir is required")
        if grade_threshold is not None:
            resolved_grade_threshold = float(grade_threshold)
        else:
            grade_text = _prompt_text(
                "Grade threshold [80.0, blank to omit]: ",
                default="",
                input_fn=input_fn,
            )
            if grade_text:
                try:
                    resolved_grade_threshold = float(grade_text)
                except ValueError as exc:
                    raise RuntimeError("Grade threshold must be numeric") from exc
            else:
                resolved_grade_threshold = None

    config = DuecheckConfig(
        canvas_url=resolved_canvas_url,
        canvas_token=stored_token,
        out_dir=resolved_out_dir,
        grade_threshold=resolved_grade_threshold,
        token_env=resolved_token_env,
    )
    save_result = save_config(config, path=resolved_config_path, env=env_map, platform_name=platform_name)
    for warning in save_result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    saved_fields = ["canvas_url", "out_dir"]
    if config.grade_threshold is not None:
        saved_fields.append("grade_threshold")
    if config.token_env:
        saved_fields.append("token_env")
    if config.canvas_token:
        saved_fields.append("canvas_token")

    return {
        "status": "initialized",
        "config_path": str(save_result.path),
        "saved_fields": saved_fields,
        "token_storage": "config" if config.canvas_token else f"env:{config.token_env or DEFAULT_TOKEN_ENV}",
    }


def run_pull(
    canvas_url: str,
    token: str,
    out_dir: Path,
    *,
    course_filter: list[str] | None = None,
    grade_threshold: float = 80.0,
    now: datetime | None = None,
    urlopen_fn: Callable | None = None,
) -> dict:
    """Execute a full pull: courses, assignments, ledger, delta, risk."""
    now = now or datetime.now(timezone.utc)
    pulled_ts = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    kwargs: dict = {"course_filter": course_filter}
    if urlopen_fn is not None:
        kwargs["urlopen_fn"] = urlopen_fn
    adapter = CanvasAdapter(canvas_url, token, **kwargs)
    courses = adapter.get_courses()
    due_48h, due_7d = adapter.get_due_items(now)
    missing_raw = adapter.get_missing_submissions()
    course_ids = {c.id for c in courses}

    existing_ledger = load_existing_ledger(out_dir / "ledger.json")

    ledger = build_ledger(
        pulled_ts=pulled_ts,
        due_48_items=due_48h,
        due_7_items=due_7d,
        missing_raw=missing_raw,
        course_ids=course_ids,
        course_name_by_id=adapter.course_name_by_id,
        course_snapshot_by_name={course.name: course for course in courses},
        existing_ledger=existing_ledger,
        source_adapter="canvas",
    )

    delta = build_delta(existing_ledger, ledger, pulled_ts, source_adapter="canvas")
    changes_md = render_delta_markdown(delta, pulled_ts)
    risk = compute_overall_risk(
        courses,
        missing_raw,
        now,
        grade_threshold=grade_threshold,
        source_adapter="canvas",
    )

    _write_pull_artifacts(
        out_dir,
        pulled_ts=pulled_ts,
        ledger=ledger,
        delta=delta,
        changes_md=changes_md,
        risk=risk,
    )

    ledger_payload = serialize_payload(ledger)
    delta_payload = serialize_payload(delta)
    risk_payload = serialize_payload(risk)
    return {
        "pulled_at": pulled_ts,
        "courses": len(courses),
        "due_48h": len(due_48h),
        "due_7d": len(due_7d),
        "missing": len(missing_raw),
        "ledger_entries": len(ledger_payload),
        "ledger_active": sum(1 for item in ledger_payload if item.get("status") != "not_observed"),
        "delta_new": delta_payload["counts"]["new"],
        "delta_escalated": delta_payload["counts"]["escalated"],
        "delta_cleared": delta_payload["counts"]["cleared"],
        "risk_overall": risk_payload["overall"],
    }


def run_doctor(
    out_dir: Path,
    *,
    check_auth: bool = False,
    env: dict[str, str] | None = None,
    urlopen_fn: Callable | None = None,
) -> tuple[dict, int]:
    env_map = os.environ.copy() if env is None else dict(env)
    resolved_config_path = config_path(env_map)
    checks: list[dict[str, str]] = []

    try:
        loaded_config = resolve_runtime_settings(
            canvas_url=None,
            canvas_token=None,
            token_env=None,
            out_dir=str(out_dir),
            course_filter=None,
            grade_threshold=None,
            env=env_map,
            path=resolved_config_path,
        )
        if loaded_config.config_present:
            checks.append({
                "name": "config",
                "status": "PASS",
                "detail": f"Loaded config from {loaded_config.config_path}",
            })
        else:
            checks.append({
                "name": "config",
                "status": "WARN",
                "detail": f"No config found at {loaded_config.config_path}",
            })
    except RuntimeError as exc:
        loaded_config = None
        checks.append({
            "name": "config",
            "status": "FAIL",
            "detail": str(exc),
        })

    if loaded_config is None:
        token_source = ""
        token_env_name = DEFAULT_TOKEN_ENV
    else:
        token_source = loaded_config.token_source
        token_env_name = loaded_config.token_env_name

    if token_source:
        checks.append({
            "name": "token",
            "status": "PASS",
            "detail": f"Resolved token source: {token_source}",
        })
    else:
        checks.append({
            "name": "token",
            "status": "WARN",
            "detail": f"No token resolved (checked {token_env_name})",
        })

    out_status, out_detail = _doctor_probe_directory(out_dir)
    checks.append({"name": "out_dir", "status": out_status, "detail": out_detail})

    asset_status, asset_detail = _doctor_packaged_assets_status()
    checks.append({"name": "assets", "status": asset_status, "detail": asset_detail})

    artifact_status, artifact_detail = _doctor_artifact_status(out_dir)
    checks.append({"name": "artifacts", "status": artifact_status, "detail": artifact_detail})

    if check_auth:
        if loaded_config is None or not loaded_config.canvas_url or not loaded_config.token:
            checks.append({
                "name": "auth",
                "status": "FAIL",
                "detail": "Auth check requested but URL/token could not be resolved",
            })
        else:
            try:
                adapter_kwargs: dict[str, object] = {}
                if urlopen_fn is not None:
                    adapter_kwargs["urlopen_fn"] = urlopen_fn
                adapter = CanvasAdapter(
                    loaded_config.canvas_url,
                    loaded_config.token,
                    **adapter_kwargs,
                )
                course_count = len(adapter.get_courses())
            except Exception as exc:
                checks.append({
                    "name": "auth",
                    "status": "FAIL",
                    "detail": str(exc),
                })
            else:
                checks.append({
                    "name": "auth",
                    "status": "PASS",
                    "detail": f"Canvas auth succeeded ({course_count} courses)",
                })

    exit_code = _doctor_exit_code(checks)
    return (
        {
            "config_path": str(resolved_config_path),
            "out_dir": str(out_dir),
            "checks": checks,
        },
        exit_code,
    )


def run_repair(out_dir: Path) -> dict:
    """Rebuild delta and changes markdown from an existing ledger."""
    ledger_path = out_dir / "ledger.json"
    if not ledger_path.exists():
        return {"status": "skipped", "reason": "no ledger.json found"}

    try:
        ledger = json.loads(ledger_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"status": "error", "reason": "failed to parse ledger.json"}

    if not isinstance(ledger, list):
        return {"status": "error", "reason": "ledger.json is not a list"}

    repaired_ledger = [
        ledger_entry_from_mapping(item, default_source_adapter="repair")
        for item in ledger
        if isinstance(item, dict)
    ]
    pulled_ts = resolve_repair_pulled_ts(out_dir / "pulled_at.txt", ledger)
    _snapshot_existing_run(out_dir)
    previous_pulled_ts, previous_ledger = _load_previous_run_ledger(out_dir, pulled_ts)
    if previous_pulled_ts is None or previous_ledger is None:
        return {"status": "skipped", "reason": "no prior run snapshot found"}

    delta = build_delta(previous_ledger, repaired_ledger, pulled_ts, source_adapter="repair")
    changes_md = render_delta_markdown(delta, pulled_ts)
    risk_path = out_dir / "risk.json"
    if risk_path.exists():
        try:
            raw_risk = json.loads(risk_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("failed to parse risk.json") from exc
        if not isinstance(raw_risk, dict):
            raise RuntimeError("risk.json is not an object")
        risk = risk_report_from_mapping(raw_risk, default_source_adapter="repair")
    else:
        risk = risk_report_from_mapping(
            {
                "overall": "UNKNOWN",
                "course_risks": {},
                "missing_risk": "UNKNOWN",
                "flagged_courses": [],
                "missing_count": 0,
            },
            default_source_adapter="repair",
        )

    _write_pull_artifacts(
        out_dir,
        pulled_ts=pulled_ts,
        ledger=repaired_ledger,
        delta=delta,
        changes_md=changes_md,
        risk=risk,
    )

    delta_payload = serialize_payload(delta)
    return {
        "status": "repaired",
        "ledger_entries": len(repaired_ledger),
        "compared_to": previous_pulled_ts,
        "counts": delta_payload["counts"],
    }


def run_demo(out_dir: Path, *, open_browser: bool = False) -> dict:
    bundle = _load_demo_bundle()
    pulled_ts = str(bundle.get("pulled_at") or "")
    raw_ledger = bundle.get("ledger")
    raw_delta = bundle.get("delta")
    raw_risk = bundle.get("risk")
    if (
        not pulled_ts
        or not isinstance(raw_ledger, list)
        or not isinstance(raw_delta, dict)
        or not isinstance(raw_risk, dict)
    ):
        raise RuntimeError("Demo bundle is incomplete")

    ledger = [
        ledger_entry_from_mapping(item, default_source_adapter="demo")
        for item in raw_ledger
        if isinstance(item, dict)
    ]
    delta = delta_report_from_mapping(raw_delta, default_source_adapter="demo")
    risk = risk_report_from_mapping(raw_risk, default_source_adapter="demo")
    changes_md = render_delta_markdown(delta, pulled_ts)
    _write_pull_artifacts(
        out_dir,
        pulled_ts=pulled_ts,
        ledger=ledger,
        delta=delta,
        changes_md=changes_md,
        risk=risk,
    )
    report_path = write_report_html(out_dir)
    opened_browser = _open_report_in_browser(report_path) if open_browser else False
    risk_payload = serialize_payload(risk)

    return {
        "status": "demo_ready",
        "pulled_at": pulled_ts,
        "out_dir": str(out_dir),
        "report_html": str(report_path),
        "opened_browser": opened_browser,
        "ledger_entries": len(ledger),
        "risk_overall": risk_payload.get("overall", "UNKNOWN"),
    }


def run_report(
    out_dir: Path,
    *,
    html: bool,
    output_path: Path | None = None,
    open_browser: bool = False,
) -> dict:
    if not html:
        raise RuntimeError("Only --html is currently supported")

    report_path = write_report_html(out_dir, output_path)
    opened_browser = _open_report_in_browser(report_path) if open_browser else False
    return {
        "status": "report_ready",
        "format": "html",
        "out_dir": str(out_dir),
        "output": str(report_path),
        "opened_browser": opened_browser,
    }


def run_redact(out_dir: Path, dest: Path) -> dict:
    bundle = build_redacted_bundle(out_dir)
    ledger_payload = serialize_payload(bundle.ledger)
    delta_payload = serialize_payload(bundle.delta)
    risk_payload = serialize_payload(bundle.risk)
    _validate_payload_bundle(ledger_payload, delta_payload, risk_payload)

    dest.mkdir(parents=True, exist_ok=True)
    _write_artifact_bundle(
        dest,
        pulled_ts=bundle.pulled_at,
        ledger=ledger_payload,
        delta=delta_payload,
        changes_md=bundle.changes_md,
        risk=risk_payload,
    )
    report_path = write_report_html(dest)
    required_outputs = {
        "ledger.json",
        "delta.json",
        "risk.json",
        "changes.md",
        "pulled_at.txt",
        "report.html",
    }
    missing_outputs = [name for name in required_outputs if not (dest / name).exists()]
    if not report_path.exists() or missing_outputs:
        detail = ", ".join(sorted(set(missing_outputs + (["report.html"] if not report_path.exists() else []))))
        raise RuntimeError(f"Redacted bundle is incomplete: missing {detail}")

    results, exit_code = run_verify(dest)
    if exit_code != 0:
        failures = {name: errors for name, errors in results.items() if errors}
        raise RuntimeError(f"Redacted bundle failed validation: {failures}")

    return {
        "status": "redacted",
        "source_out_dir": str(out_dir),
        "dest": str(dest),
        "report_html": str(report_path),
        "ledger_entries": len(ledger_payload),
    }


def run_verify(out_dir: Path) -> tuple[dict[str, list[str]], int]:
    results = validate_artifacts(out_dir)
    exit_code = 0 if all(not errors for errors in results.values()) else 1
    return results, exit_code


def _should_exit_on_threshold(
    *,
    fail_on: str,
    summary: dict,
    delta_payload: dict,
    risk_payload: dict,
) -> bool:
    token = fail_on.strip().lower()
    if not token:
        return False
    if token == "high":
        return str(risk_payload.get("overall") or "").upper() == "HIGH"
    if token == "medium":
        return str(risk_payload.get("overall") or "").upper() in {"MEDIUM", "HIGH"}
    if token == "escalated":
        return int(delta_payload.get("counts", {}).get("escalated", 0)) > 0
    if token == "missing":
        return int(summary.get("missing", 0)) > 0
    raise RuntimeError(f"Unsupported --fail-on value: {fail_on}")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]

    if argv and argv[0] == "init":
        args = parse_init_args(argv[1:])
        try:
            result = run_init(
                canvas_url=args.canvas_url,
                canvas_token=args.canvas_token,
                token_env=args.token_env,
                out_dir=args.out_dir,
                grade_threshold=args.grade_threshold,
                yes=args.yes,
                print_path=args.print_path,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if result["status"] == "config_path":
            print(result["config_path"])
        else:
            print(
                f"INIT: wrote {result['config_path']} "
                f"fields={','.join(result['saved_fields'])} token={result['token_storage']}"
            )
        return 0

    if argv and argv[0] == "demo":
        args = parse_demo_args(argv[1:])
        out_dir = Path(args.out_dir).expanduser().resolve()
        try:
            result = run_demo(out_dir, open_browser=args.open_browser)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(
                f"DEMO: wrote sample artifacts to {result['out_dir']}, "
                f"report={result['report_html']}, risk={result['risk_overall']}"
            )
        return 0

    if argv and argv[0] == "doctor":
        args = parse_doctor_args(argv[1:])
        if args.out_dir:
            out_dir = Path(args.out_dir).expanduser().resolve()
        else:
            try:
                resolved_settings = resolve_runtime_settings(
                    canvas_url=None,
                    canvas_token=None,
                    token_env=None,
                    out_dir=None,
                    course_filter=None,
                    grade_threshold=None,
                )
                out_dir = Path(resolved_settings.out_dir).expanduser().resolve()
            except Exception:
                out_dir = Path(".").expanduser().resolve()
        try:
            result, exit_code = run_doctor(out_dir, check_auth=args.check_auth)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            for check in result["checks"]:
                print(f"{check['status']}: {check['name']} | {check['detail']}")
        return exit_code

    if argv and argv[0] == "redact":
        args = parse_redact_args(argv[1:])
        out_dir = Path(args.out_dir).expanduser().resolve()
        dest = Path(args.dest).expanduser().resolve()
        try:
            result = run_redact(out_dir, dest)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"REDACT: wrote {result['dest']} report={result['report_html']}")
        return 0

    if argv and argv[0] == "verify":
        args = parse_verify_args(argv[1:])
        out_dir = Path(args.out_dir).expanduser().resolve()
        try:
            results, exit_code = run_verify(out_dir)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(results, indent=2))
        else:
            failures = {name: errors for name, errors in results.items() if errors}
            if not failures:
                print(f"VERIFY: {out_dir} valid")
            else:
                for name, errors in failures.items():
                    print(f"{name}:")
                    for error in errors:
                        print(f"  - {error}")
        return exit_code

    if argv and argv[0] == "schedule":
        args = parse_schedule_args(argv[1:])
        try:
            if args.schedule_command == "install":
                result = install_schedule(
                    hour=args.hour,
                    minute=args.minute,
                    canvas_url=args.canvas_url,
                    canvas_token=args.canvas_token,
                    token_env=args.token_env,
                    out_dir=args.out_dir,
                    course_filter=args.course_filter,
                    grade_threshold=args.grade_threshold,
                )
            elif args.schedule_command == "status":
                result = schedule_status()
            else:
                result = remove_schedule()
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        if args.json_output:
            print(json.dumps(result, indent=2))
        elif args.schedule_command == "install":
            print(
                f"SCHEDULE: installed {result['label']} at {result['hour']:02d}:{result['minute']:02d} "
                f"plist={result['plist_path']} token={result['token_storage']}"
            )
        elif args.schedule_command == "status":
            if result["status"] == "installed":
                state = "loaded" if result.get("loaded") else "present"
                print(
                    f"SCHEDULE: {state} {result['label']} at "
                    f"{result['hour']:02d}:{result['minute']:02d} plist={result['plist_path']}"
                )
            else:
                detail = result.get("detail", result["status"])
                print(f"SCHEDULE: {detail}")
        else:
            print(f"SCHEDULE: {result['status']}")
        return 0

    if argv and argv[0] == "report":
        args = parse_report_args(argv[1:])
        out_dir = Path(args.out_dir).expanduser().resolve()
        output_path = Path(args.output).expanduser().resolve() if args.output else None
        try:
            result = run_report(
                out_dir,
                html=args.html,
                output_path=output_path,
                open_browser=args.open_browser,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"REPORT: html -> {result['output']}")
        return 0

    args = parse_pull_args(argv)
    try:
        settings = resolve_runtime_settings(
            canvas_url=args.canvas_url,
            canvas_token=args.canvas_token,
            token_env=args.token_env,
            out_dir=args.out_dir,
            course_filter=args.course_filter,
            grade_threshold=args.grade_threshold,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out_dir = Path(settings.out_dir).expanduser().resolve()

    if args.repair:
        result = run_repair(out_dir)
        if args.json_output:
            print(json.dumps(result, indent=2))
        elif result["status"] == "repaired":
            counts = result["counts"]
            print(
                f"REPAIR: {result['ledger_entries']} entries, "
                f"new={counts['new']}, escalated={counts['escalated']}, "
                f"cleared={counts['cleared']}"
            )
        else:
            print(f"REPAIR: {result.get('reason', result['status'])}")
        return 0

    canvas_url = settings.canvas_url
    if not canvas_url:
        print(
            "ERROR: Canvas URL not resolved. Run 'duecheck init' or set CANVAS_URL / --canvas-url.",
            file=sys.stderr,
        )
        return 1

    token = settings.token
    if not token:
        print(
            "ERROR: Canvas token not resolved. Run 'duecheck init', set CANVAS_TOKEN, or use --token-env.",
            file=sys.stderr,
        )
        return 1

    try:
        summary = run_pull(
            canvas_url=canvas_url,
            token=token,
            out_dir=out_dir,
            course_filter=settings.course_filter,
            grade_threshold=settings.grade_threshold,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    delta_payload = json.loads((out_dir / "delta.json").read_text())
    risk_payload = json.loads((out_dir / "risk.json").read_text())
    if _should_exit_on_threshold(
        fail_on=args.fail_on,
        summary=summary,
        delta_payload=delta_payload,
        risk_payload=risk_payload,
    ):
        if args.json_output:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"PULL: {summary['courses']} courses, "
                f"{summary['due_48h']} due_48h, {summary['due_7d']} due_7d, "
                f"{summary['missing']} missing, risk={summary['risk_overall']}"
            )
        return 2

    if args.json_output:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"PULL: {summary['courses']} courses, "
            f"{summary['due_48h']} due_48h, {summary['due_7d']} due_7d, "
            f"{summary['missing']} missing, risk={summary['risk_overall']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
