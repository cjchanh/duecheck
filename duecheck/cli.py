"""DueCheck CLI — pull Canvas data and compute academic risk."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .adapter import CanvasAdapter
from .delta import build_delta, render_delta_markdown
from .ledger import build_ledger, load_existing_ledger, resolve_repair_pulled_ts
from .risk import compute_overall_risk


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="duecheck",
        description="Canvas early warning engine — pull assignments and compute risk.",
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

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    (out_dir / "delta.json").write_text(json.dumps(delta, indent=2) + "\n")
    (out_dir / "changes.md").write_text(changes_md)
    (out_dir / "risk.json").write_text(json.dumps(risk, indent=2) + "\n")
    (out_dir / "pulled_at.txt").write_text(pulled_ts + "\n")

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
    existing = load_existing_ledger(ledger_path)
    delta = build_delta(existing, ledger, pulled_ts)
    changes_md = render_delta_markdown(delta, pulled_ts)

    (out_dir / "delta.json").write_text(json.dumps(delta, indent=2) + "\n")
    (out_dir / "changes.md").write_text(changes_md)

    return {
        "status": "repaired",
        "ledger_entries": len(ledger),
        "counts": delta["counts"],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
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
