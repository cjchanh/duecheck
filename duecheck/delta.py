"""Delta computation: track what changed between sync runs."""

from __future__ import annotations

from .renderers.markdown import render_delta_markdown as _render_delta_markdown
from .types import (
    LEDGER_STATUS_PRIORITY,
    ArtifactMeta,
    DeltaChange,
    DeltaReport,
    match_entry,
    serialize_payload,
)


def build_delta(
    previous_ledger: dict[str, dict],
    current_ledger: list[dict],
    pulled_ts: str,
    *,
    source_adapter: str = "canvas",
) -> DeltaReport:
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
    changes: list[DeltaChange] = []

    for current in current_ledger:
        current_item = serialize_payload(current)
        item_id = str(current_item.get("item_id") or "")
        if not item_id:
            continue
        _, previous = match_entry(
            previous_ledger,
            course=str(current_item.get("course") or ""),
            name=str(current_item.get("name") or ""),
            source_key=str(current_item.get("source_key") or "") or None,
            item_id=item_id,
        )
        from_status = str(previous.get("status") or "absent") if previous else "absent"
        to_status = str(current_item.get("status") or "not_observed")
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
        from_due_at = str(previous.get("due_at") or "") if previous else ""
        to_due_at = str(current_item.get("due_at") or "")
        changes.append(
            DeltaChange(
                item_id=item_id,
                name=str(current_item.get("name") or ""),
                course=str(current_item.get("course") or ""),
                change_type=change_type,
                from_status=from_status,
                to_status=to_status,
                from_due_at=from_due_at,
                to_due_at=to_due_at,
                due_at_changed=from_due_at != to_due_at,
                first_seen=str(current_item.get("first_seen") or ""),
                last_seen=str(current_item.get("last_seen") or ""),
                severity_label=str(current_item.get("severity_label") or current_item.get("confidence") or ""),
            )
        )

    return DeltaReport(
        meta=ArtifactMeta.for_source(source_adapter),
        pulled_at=pulled_ts,
        counts=counts,
        changes=changes,
    )


def render_delta_markdown(delta: DeltaReport | dict, pulled_ts: str) -> str:
    return _render_delta_markdown(delta, pulled_ts)
