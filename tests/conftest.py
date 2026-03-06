"""Shared test fixtures for DueCheck tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from duecheck.types import CourseInfo


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_courses() -> list[CourseInfo]:
    return [
        CourseInfo(id=101, name="English Composition", slug="ENGL", score=92.0, grade="A-"),
        CourseInfo(id=102, name="Philosophy", slug="PHIL", score=74.0, grade="C"),
        CourseInfo(id=103, name="Health Nutrition", slug="HPNU", score=None, grade=None),
    ]


class FakeResponse:
    """Fake HTTP response for Canvas API testing."""

    def __init__(self, payload: Any, link_header: str = "") -> None:
        self._payload = payload
        self.headers = {"Link": link_header}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass


def make_urlopen(responses: dict[str, Any]):
    """Create a fake urlopen that returns canned responses keyed by URL substring.

    Keys are matched longest-first so 'assignments' beats 'courses' when
    the URL is 'courses/101/assignments'.
    """
    sorted_keys = sorted(responses.keys(), key=len, reverse=True)

    def fake_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for key in sorted_keys:
            if key in url:
                return FakeResponse(responses[key])
        return FakeResponse([])
    return fake_urlopen
