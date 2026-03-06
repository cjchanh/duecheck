"""LMS adapter implementations. Canvas is the default."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request
from urllib.request import urlopen as _urlopen

from .types import AssignmentObservation, CourseInfo, LMSAdapter, parse_datetime


def _parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        chunk = part.strip()
        if 'rel="next"' not in chunk:
            continue
        m = re.search(r"<([^>]+)>", chunk)
        if m:
            return m.group(1)
    return None


def _canvas_get(
    endpoint: str,
    token: str,
    canvas_url: str,
    urlopen_fn: Callable = _urlopen,
) -> list | dict:
    base = canvas_url.rstrip("/") + "/"
    next_url = urljoin(base, f"api/v1/{endpoint.lstrip('/')}")
    aggregated: list = []

    while next_url:
        req = Request(next_url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urlopen_fn(req) as resp:
                payload = json.loads(resp.read() or b"null")
                if isinstance(payload, list):
                    aggregated.extend(payload)
                    next_url = _parse_next_link(resp.headers.get("Link", ""))
                else:
                    return payload
        except HTTPError as exc:
            raise RuntimeError(f"Canvas HTTP error {exc.code} for '{endpoint}'") from exc
        except URLError as exc:
            raise RuntimeError(f"Canvas network error for '{endpoint}': {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Canvas invalid JSON for '{endpoint}'") from exc

    return aggregated


def _normalize_course_name(raw_name: str) -> str:
    name = raw_name.strip()
    name = re.sub(r"\s+\([^)]*\)\s*$", "", name)
    return name


def _score_grade_from_course(course: dict) -> tuple[float | None, str | None]:
    enrollments = course.get("enrollments") or []
    for enr in enrollments:
        if not isinstance(enr, dict):
            continue
        score = enr.get("computed_current_score")
        grade = enr.get("computed_current_grade")
        if isinstance(score, (int, float)) or isinstance(grade, str):
            return (
                float(score) if isinstance(score, (int, float)) else None,
                grade if isinstance(grade, str) else None,
            )
    return (None, None)


def _assignment_is_submitted(assignment: dict) -> bool:
    submission = assignment.get("submission") or {}
    if not isinstance(submission, dict):
        return False
    if submission.get("excused") is True:
        return True
    if submission.get("submitted_at"):
        return True
    workflow = (submission.get("workflow_state") or "").lower()
    return workflow in {"submitted", "graded", "pending_review", "complete"}


def _canvas_assignment_source_key(course_id: int, assignment: dict) -> str | None:
    for field in ("assignment_id", "id"):
        raw_value = assignment.get(field)
        if isinstance(raw_value, int):
            return f"canvas:{course_id}:{raw_value}"
        if isinstance(raw_value, str) and raw_value.strip():
            return f"canvas:{course_id}:{raw_value.strip()}"
    return None


class CanvasAdapter:
    """Canvas LMS adapter implementing the LMSAdapter protocol."""

    def __init__(
        self,
        canvas_url: str,
        token: str,
        *,
        course_filter: list[str] | None = None,
        urlopen_fn: Callable = _urlopen,
    ) -> None:
        self.canvas_url = canvas_url
        self.token = token
        self.course_filter = course_filter
        self.urlopen_fn = urlopen_fn
        self._courses: list[CourseInfo] | None = None
        self._course_name_by_id: dict[int, str] = {}

    def _api(self, endpoint: str) -> list | dict:
        return _canvas_get(endpoint, self.token, self.canvas_url, self.urlopen_fn)

    def _make_slug(self, name: str) -> str:
        if self.course_filter:
            for token in self.course_filter:
                if token in name:
                    return token.replace(" ", "")
        slug = re.sub(r"[^A-Za-z0-9]+", "", name)
        return slug.upper() if slug else "COURSE"

    def get_courses(self) -> list[CourseInfo]:
        if self._courses is not None:
            return self._courses

        raw = self._api("courses?enrollment_state=active&include[]=total_scores&per_page=100")
        if not isinstance(raw, list):
            raise RuntimeError("Unexpected courses payload shape")

        parsed: list[CourseInfo] = []
        for c in raw:
            course_id = c.get("id")
            name = c.get("name")
            if not isinstance(course_id, int) or not isinstance(name, str):
                continue
            norm = _normalize_course_name(name)
            score, grade = _score_grade_from_course(c)
            parsed.append(CourseInfo(
                id=course_id,
                name=norm,
                slug=self._make_slug(norm),
                score=score,
                grade=grade,
            ))

        if self.course_filter:
            targeted = [c for c in parsed if any(tok in c.name for tok in self.course_filter)]
            if targeted:
                parsed = targeted

        self._courses = sorted(parsed, key=lambda c: c.name.lower())
        self._course_name_by_id = {c.id: c.name for c in self._courses}
        return self._courses

    def get_assignments(self, course_id: int) -> list[dict]:
        raw = self._api(
            f"courses/{course_id}/assignments?include[]=submission&order_by=due_at&per_page=100"
        )
        return raw if isinstance(raw, list) else []

    def get_unsubmitted_assignments(
        self, course_id: int, now: datetime | None = None
    ) -> list[AssignmentObservation]:
        """Return unsubmitted assignments with stable source keys when available."""
        now = now or datetime.now(timezone.utc)
        courses = self.get_courses()
        course_name = next((c.name for c in courses if c.id == course_id), f"course:{course_id}")
        items: list[AssignmentObservation] = []

        for a in self.get_assignments(course_id):
            if not isinstance(a, dict):
                continue
            if _assignment_is_submitted(a):
                continue
            due_dt = parse_datetime(a.get("due_at"))
            if due_dt is None:
                continue
            name = str(a.get("name") or "Unnamed assignment")
            items.append(AssignmentObservation(
                source_key=_canvas_assignment_source_key(course_id, a),
                due_at=due_dt,
                course=course_name,
                name=name,
            ))
        return items

    def get_due_items(
        self, now: datetime | None = None
    ) -> tuple[list[AssignmentObservation], list[AssignmentObservation]]:
        """Return (due_48h_items, due_7d_items) across all courses."""
        now = now or datetime.now(timezone.utc)
        due_48h: list[AssignmentObservation] = []
        due_7d: list[AssignmentObservation] = []

        for course in self.get_courses():
            for observation in self.get_unsubmitted_assignments(course.id, now):
                if now < observation.due_at <= now + timedelta(hours=48):
                    due_48h.append(observation)
                elif now + timedelta(hours=48) < observation.due_at <= now + timedelta(days=7):
                    due_7d.append(observation)

        return (
            sorted(due_48h, key=lambda x: (x.due_at, x.course.lower(), x.name.lower())),
            sorted(due_7d, key=lambda x: (x.due_at, x.course.lower(), x.name.lower())),
        )

    def get_missing_submissions(self) -> list[dict]:
        raw = self._api("users/self/missing_submissions?per_page=100")
        if not isinstance(raw, list):
            return []
        course_ids = {c.id for c in self.get_courses()}
        if not course_ids:
            return raw
        return [
            m for m in raw
            if isinstance(m, dict) and (
                not isinstance(m.get("course_id"), int) or m["course_id"] in course_ids
            )
        ]

    @property
    def course_name_by_id(self) -> dict[int, str]:
        self.get_courses()
        return self._course_name_by_id


# Protocol compliance check
assert isinstance(CanvasAdapter.__new__(CanvasAdapter), LMSAdapter)
