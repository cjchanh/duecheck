"""DueCheck CLI — pull Canvas data and compute academic risk."""

from __future__ import annotations

import argparse
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
from .delta import build_delta, render_delta_markdown
from .ledger import build_ledger, load_existing_ledger, resolve_repair_pulled_ts
from .report import write_report_html
from .risk import compute_overall_risk
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
            "Extra commands: 'duecheck demo --out-dir DIR', "
            "'duecheck report --html --out-dir DIR', and 'duecheck verify --out-dir DIR'."
        ),
    )
    parser.add_argument(
        "--canvas-url",
        default=os.environ.get("CANVAS_URL", ""),
        help="Canvas base URL (or set CANVAS_URL env var)",
    )
    parser.add_argument(
        "--token-env",
        default="CANVAS_TOKEN",
        help="Environment variable name containing Canvas API token",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
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
        default=80.0,
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
    out_dir = Path(args.out_dir).expanduser().resolve()

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

    canvas_url = args.canvas_url
    if not canvas_url:
        print("ERROR: --canvas-url required (or set CANVAS_URL env var)", file=sys.stderr)
        return 1

    token = os.environ.get(args.token_env)
    if not token:
        print(f"ERROR: env var '{args.token_env}' is not set", file=sys.stderr)
        return 1

    try:
        summary = run_pull(
            canvas_url=canvas_url,
            token=token,
            out_dir=out_dir,
            course_filter=args.course_filter,
            grade_threshold=args.grade_threshold,
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
