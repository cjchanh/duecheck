"""Markdown renderers for DueCheck artifacts."""

from __future__ import annotations

from ..types import DeltaReport, serialize_payload


def render_delta_markdown(delta: DeltaReport | dict, pulled_ts: str) -> str:
    """Render a delta as human-readable markdown."""
    delta_payload = serialize_payload(delta)
    counts = delta_payload.get("counts", {})
    changes = delta_payload.get("changes", [])
    sections = [
        ("New Items", "new"),
        ("Reactivated Items", "reactivated"),
        ("Escalated Items", "escalated"),
        ("De-escalated Items", "de_escalated"),
        ("Cleared Items", "cleared"),
    ]

    lines = [
        "# Assignment Changes",
        f"_Pulled: {pulled_ts}_",
        "",
        "## Summary",
        f"- new: {counts.get('new', 0)}",
        f"- reactivated: {counts.get('reactivated', 0)}",
        f"- escalated: {counts.get('escalated', 0)}",
        f"- de_escalated: {counts.get('de_escalated', 0)}",
        f"- cleared: {counts.get('cleared', 0)}",
        f"- unchanged_active: {counts.get('unchanged_active', 0)}",
        f"- unchanged_inactive: {counts.get('unchanged_inactive', 0)}",
        "",
    ]

    for heading, change_type in sections:
        lines.append(f"## {heading}")
        matched = [item for item in changes if item.get("change_type") == change_type]
        if not matched:
            lines.append("_None_")
            lines.append("")
            continue
        for item in matched:
            due_at = str(item.get("to_due_at") or item.get("from_due_at") or "")
            due_text = due_at[:10] if due_at else "NO-DUE-DATE"
            lines.append(
                f"- {due_text} | {item.get('course', '')} | {item.get('name', '')} | "
                f"{item.get('from_status', 'absent')} -> {item.get('to_status', '')}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
