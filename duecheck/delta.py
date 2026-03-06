"""Delta computation: track what changed between sync runs."""

from __future__ import annotations

from .types import LEDGER_STATUS_PRIORITY


def build_delta(
    previous_ledger: dict[str, dict],
    current_ledger: list[dict],
    pulled_ts: str,
) -> dict:
    """Compare previous and current ledger to produce a structured delta."""
    counts = {
        "new": 0,
        "reactivated": 0,
        "escalated": 0,
        "de_escalated": 0,
        "cleared": 0,
        "unchanged_active": 0,
        "unchanged_inactive": 0,
    }
    changes: list[dict] = []

    for current in current_ledger:
        item_id = str(current.get("item_id") or "")
        if not item_id:
            continue
        previous = previous_ledger.get(item_id)
        from_status = str(previous.get("status") or "absent") if previous else "absent"
        to_status = str(current.get("status") or "not_observed")
        from_rank = LEDGER_STATUS_PRIORITY.get(from_status, -1)
        to_rank = LEDGER_STATUS_PRIORITY.get(to_status, -1)

        if previous is None:
            change_type = "new"
        elif from_status == "not_observed" and to_status != "not_observed":
            change_type = "reactivated"
        elif from_status != "not_observed" and to_status == "not_observed":
            change_type = "cleared"
        elif to_rank > from_rank:
            change_type = "escalated"
        elif to_rank < from_rank:
            change_type = "de_escalated"
        elif to_status == "not_observed":
            change_type = "unchanged_inactive"
        else:
            change_type = "unchanged_active"

        counts[change_type] += 1
        changes.append(
            {
                "item_id": item_id,
                "name": str(current.get("name") or ""),
                "course": str(current.get("course") or ""),
                "change_type": change_type,
                "from_status": from_status,
                "to_status": to_status,
                "from_due_at": str(previous.get("due_at") or "") if previous else "",
                "to_due_at": str(current.get("due_at") or ""),
                "due_at_changed": (
                    (str(previous.get("due_at") or "") if previous else "")
                    != str(current.get("due_at") or "")
                ),
                "first_seen": str(current.get("first_seen") or ""),
                "last_seen": str(current.get("last_seen") or ""),
                "confidence": str(current.get("confidence") or ""),
            }
        )

    return {
        "pulled_at": pulled_ts,
        "counts": counts,
        "changes": changes,
    }


def render_delta_markdown(delta: dict, pulled_ts: str) -> str:
    """Render a delta as human-readable markdown."""
    counts = delta.get("counts", {})
    changes = delta.get("changes", [])
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
