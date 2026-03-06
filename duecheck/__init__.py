"""DueCheck — Canvas early warning engine."""

__version__ = "0.2.0"

from .adapter import CanvasAdapter
from .delta import build_delta
from .ledger import build_ledger, load_existing_ledger
from .renderers import load_report_context, render_delta_markdown, render_report_html, write_report_html
from .risk import compute_overall_risk, score_course_risk
from .types import AssignmentObservation, CourseInfo, LMSAdapter

__all__ = [
    "CanvasAdapter",
    "AssignmentObservation",
    "CourseInfo",
    "LMSAdapter",
    "build_delta",
    "build_ledger",
    "compute_overall_risk",
    "load_existing_ledger",
    "load_report_context",
    "render_delta_markdown",
    "render_report_html",
    "score_course_risk",
    "write_report_html",
]
