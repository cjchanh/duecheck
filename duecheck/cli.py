"""DueCheck CLI — pull Canvas data and compute academic risk."""

from __future__ import annotations

import argparse
import importlib.resources as resources
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .adapter import CanvasAdapter
from .delta import build_delta, render_delta_markdown
from .ledger import build_ledger, load_existing_ledger, resolve_repair_pulled_ts
from .report import write_report_html
from .risk import compute_overall_risk

ARTIFACT_JSON_FILES = ("ledger.json", "delta.json", "risk.json")
ARTIFACT_TEXT_FILES = ("changes.md", "pulled_at.txt")


def _write_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


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
            (run_dir / file_name).write_text(source.read_text(errors="ignore"))


def _write_pull_artifacts(
    out_dir: Path,
    *,
    pulled_ts: str,
    ledger: list[dict],
    delta: dict,
    changes_md: str,
    risk: dict,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _snapshot_existing_run(out_dir)

    _write_json(out_dir / "ledger.json", ledger)
    _write_json(out_dir / "delta.json", delta)
    (out_dir / "changes.md").write_text(changes_md)
    _write_json(out_dir / "risk.json", risk)
    (out_dir / "pulled_at.txt").write_text(pulled_ts + "\n")

    run_dir = _run_dir(out_dir, pulled_ts)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "ledger.json", ledger)
    _write_json(run_dir / "delta.json", delta)
    (run_dir / "changes.md").write_text(changes_md)
    _write_json(run_dir / "risk.json", risk)
    (run_dir / "pulled_at.txt").write_text(pulled_ts + "\n")


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
        epilog="Extra commands: 'duecheck demo --out-dir DIR' and 'duecheck report --html --out-dir DIR'.",
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
        help="Course name substrings to filter (e.g. 'ENGL 1308' 'PHIL 1000')",
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
        existing_ledger=existing_ledger,
    )

    delta = build_delta(existing_ledger, ledger, pulled_ts)
    changes_md = render_delta_markdown(delta, pulled_ts)
    risk = compute_overall_risk(courses, missing_raw, now, grade_threshold=grade_threshold)

    _write_pull_artifacts(
        out_dir,
        pulled_ts=pulled_ts,
        ledger=ledger,
        delta=delta,
        changes_md=changes_md,
        risk=risk,
    )

    return {
        "pulled_at": pulled_ts,
        "courses": len(courses),
        "due_48h": len(due_48h),
        "due_7d": len(due_7d),
        "missing": len(missing_raw),
        "ledger_entries": len(ledger),
        "ledger_active": sum(1 for item in ledger if item.get("status") != "not_observed"),
        "delta_new": delta["counts"]["new"],
        "delta_escalated": delta["counts"]["escalated"],
        "delta_cleared": delta["counts"]["cleared"],
        "risk_overall": risk["overall"],
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

    pulled_ts = resolve_repair_pulled_ts(out_dir / "pulled_at.txt", ledger)
    _snapshot_existing_run(out_dir)
    previous_pulled_ts, previous_ledger = _load_previous_run_ledger(out_dir, pulled_ts)
    if previous_pulled_ts is None or previous_ledger is None:
        return {"status": "skipped", "reason": "no prior run snapshot found"}

    delta = build_delta(previous_ledger, ledger, pulled_ts)
    changes_md = render_delta_markdown(delta, pulled_ts)

    _write_json(out_dir / "delta.json", delta)
    (out_dir / "changes.md").write_text(changes_md)
    current_run_dir = _run_dir(out_dir, pulled_ts)
    current_run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(current_run_dir / "ledger.json", ledger)
    _write_json(current_run_dir / "delta.json", delta)
    (current_run_dir / "changes.md").write_text(changes_md)
    (current_run_dir / "pulled_at.txt").write_text(pulled_ts + "\n")
    risk_path = out_dir / "risk.json"
    if risk_path.exists():
        (current_run_dir / "risk.json").write_text(risk_path.read_text(errors="ignore"))

    return {
        "status": "repaired",
        "ledger_entries": len(ledger),
        "compared_to": previous_pulled_ts,
        "counts": delta["counts"],
    }


def run_demo(out_dir: Path) -> dict:
    bundle = _load_demo_bundle()
    pulled_ts = str(bundle.get("pulled_at") or "")
    ledger = bundle.get("ledger")
    delta = bundle.get("delta")
    risk = bundle.get("risk")
    if not pulled_ts or not isinstance(ledger, list) or not isinstance(delta, dict) or not isinstance(risk, dict):
        raise RuntimeError("Demo bundle is incomplete")

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

    return {
        "status": "demo_ready",
        "pulled_at": pulled_ts,
        "out_dir": str(out_dir),
        "report_html": str(report_path),
        "ledger_entries": len(ledger),
        "risk_overall": risk.get("overall", "UNKNOWN"),
    }


def run_report(out_dir: Path, *, html: bool, output_path: Path | None = None) -> dict:
    if not html:
        raise RuntimeError("Only --html is currently supported")

    report_path = write_report_html(out_dir, output_path)
    return {
        "status": "report_ready",
        "format": "html",
        "out_dir": str(out_dir),
        "output": str(report_path),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]

    if argv and argv[0] == "demo":
        args = parse_demo_args(argv[1:])
        out_dir = Path(args.out_dir).expanduser().resolve()
        try:
            result = run_demo(out_dir)
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

    if argv and argv[0] == "report":
        args = parse_report_args(argv[1:])
        out_dir = Path(args.out_dir).expanduser().resolve()
        output_path = Path(args.output).expanduser().resolve() if args.output else None
        try:
            result = run_report(out_dir, html=args.html, output_path=output_path)
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
