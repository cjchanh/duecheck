"""Rule-based academic risk scoring. No external API dependencies."""

from __future__ import annotations

from datetime import datetime, timezone

from .types import ArtifactMeta, CourseInfo, RiskReport, parse_datetime


def score_course_risk(course: CourseInfo, *, threshold: float = 80.0) -> str:
    """Return 'HIGH', 'MEDIUM', or 'LOW' for a single course."""
    if course.score is None:
        return "MEDIUM"
    if course.score < threshold - 10:
        return "HIGH"
    if course.score < threshold:
        return "MEDIUM"
    return "LOW"


def score_missing_risk(
    missing_items: list[dict],
    now: datetime | None = None,
    *,
    stale_days: int = 3,
) -> str:
    """Return risk level based on missing submissions."""
    now = now or datetime.now(timezone.utc)
    if not missing_items:
        return "LOW"

    stale_count = 0
    for item in missing_items:
        due_dt = parse_datetime(item.get("due_at"))
        if due_dt is None:
            stale_count += 1
            continue
        days_overdue = (now - due_dt).total_seconds() / 86400
        if days_overdue > stale_days:
            stale_count += 1

    if stale_count >= 3:
        return "HIGH"
    if stale_count >= 1:
        return "MEDIUM"
    return "LOW"


def aggregate_risk(*levels: str) -> str:
    """Aggregate multiple risk levels. Highest wins."""
    priority = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
    if not levels:
        return "UNKNOWN"
    max_level = max(levels, key=lambda x: priority.get(x, 0))
    return max_level


def compute_overall_risk(
    courses: list[CourseInfo],
    missing_items: list[dict],
    now: datetime | None = None,
    *,
    grade_threshold: float = 80.0,
    source_adapter: str = "canvas",
) -> RiskReport:
    """Compute overall academic risk from courses and missing items."""
    now = now or datetime.now(timezone.utc)

    course_risks = {c.name: score_course_risk(c, threshold=grade_threshold) for c in courses}
    missing_risk = score_missing_risk(missing_items, now)
    overall = aggregate_risk(missing_risk, *course_risks.values())

    flagged_courses = [name for name, level in course_risks.items() if level in ("HIGH", "MEDIUM")]

    return RiskReport(
        meta=ArtifactMeta.for_source(source_adapter),
        overall=overall,
        course_risks=course_risks,
        missing_risk=missing_risk,
        flagged_courses=flagged_courses,
        missing_count=len(missing_items),
    )
