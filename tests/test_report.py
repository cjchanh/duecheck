"""Tests for duecheck.report."""

from pathlib import Path

from duecheck.cli import run_demo
from duecheck.report import load_report_context, render_report_html


def test_load_report_context(tmp_path: Path):
    run_demo(tmp_path)
    context = load_report_context(tmp_path)
    assert context["pulled_at"] == "2026-03-05T12:00:00Z"
    assert len(context["active_items"]) == 5
    assert context["risk"]["overall"] == "MEDIUM"


def test_render_report_html_contains_core_sections(tmp_path: Path):
    run_demo(tmp_path)
    context = load_report_context(tmp_path)
    html = render_report_html(context)
    assert "DueCheck Local Report" in html
    assert "Change Feed" in html
    assert "Active Ledger" in html
