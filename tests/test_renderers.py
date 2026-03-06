"""Tests for renderer split compatibility."""

import json
from pathlib import Path

from duecheck import load_report_context as compat_load_report_context
from duecheck import render_delta_markdown as compat_render_delta_markdown
from duecheck import render_report_html as compat_render_report_html
from duecheck.cli import run_demo
from duecheck.renderers.html import load_report_context, render_report_html
from duecheck.renderers.markdown import render_delta_markdown


def test_renderer_split_preserves_output(tmp_path: Path):
    run_demo(tmp_path)
    delta = json.loads((tmp_path / "delta.json").read_text())
    pulled_at = (tmp_path / "pulled_at.txt").read_text().strip()

    assert render_delta_markdown(delta, pulled_at) == compat_render_delta_markdown(delta, pulled_at)


def test_renderer_html_imports_preserve_output(tmp_path: Path):
    run_demo(tmp_path)
    context = load_report_context(tmp_path)
    compat_context = compat_load_report_context(tmp_path)

    assert context["pulled_at"] == compat_context["pulled_at"]
    assert render_report_html(context) == compat_render_report_html(compat_context)
