"""Compatibility shims for HTML report rendering."""

from __future__ import annotations

from .renderers.html import load_report_context, render_report_html, write_report_html

__all__ = ["load_report_context", "render_report_html", "write_report_html"]
