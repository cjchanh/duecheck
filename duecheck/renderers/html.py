"""HTML renderers for DueCheck artifact bundles."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from ..types import parse_datetime

TODAY_SECTIONS = (
    ("missing", "Overdue", "Canvas already marked these as missing."),
    ("due_48h", "Due In 48 Hours", "Handle these before the dashboard drift hides them."),
    ("due_7d", "Due This Week", "Keep the next wave visible before it turns urgent."),
)


def _active_item_sort_key(item: dict) -> tuple[int, str, str, str]:
    status_order = {"missing": 0, "due_48h": 1, "due_7d": 2, "not_observed": 3}
    due_at = str(item.get("due_at") or "9999-99-99T99:99:99Z")
    return (
        status_order.get(str(item.get("status") or ""), 9),
        due_at,
        str(item.get("course") or ""),
        str(item.get("name") or ""),
    )


def _format_due_badge(item: dict) -> str:
    due_at = parse_datetime(str(item.get("due_at") or ""))
    if due_at is None:
        return "No due date"
    return due_at.strftime("%b %d · %H:%M UTC")


def _load_json(path: Path, expected_type: type) -> dict | list:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse {path.name}") from exc
    if not isinstance(payload, expected_type):
        raise RuntimeError(f"Unexpected shape for {path.name}")
    return payload


def load_report_context(out_dir: Path) -> dict:
    ledger = _load_json(out_dir / "ledger.json", list)
    delta = _load_json(out_dir / "delta.json", dict)
    risk = _load_json(out_dir / "risk.json", dict)

    try:
        pulled_at = (out_dir / "pulled_at.txt").read_text(errors="ignore").strip()
    except OSError as exc:
        raise RuntimeError("Failed to read pulled_at.txt") from exc
    if not pulled_at:
        raise RuntimeError("pulled_at.txt is empty")

    active_items = sorted(
        [item for item in ledger if item.get("status") != "not_observed"],
        key=_active_item_sort_key,
    )
    change_buckets: dict[str, list[dict]] = {}
    for item in delta.get("changes", []):
        if not isinstance(item, dict):
            continue
        change_type = str(item.get("change_type") or "unknown")
        change_buckets.setdefault(change_type, []).append(item)

    today_sections = []
    for status, title, description in TODAY_SECTIONS:
        items = [item for item in active_items if str(item.get("status") or "") == status]
        today_sections.append(
            {
                "status": status,
                "title": title,
                "description": description,
                "items": items,
            }
        )

    return {
        "pulled_at": pulled_at,
        "ledger": ledger,
        "delta": delta,
        "risk": risk,
        "active_items": active_items,
        "change_buckets": change_buckets,
        "today_sections": today_sections,
    }


def _tone_for_risk(level: str) -> str:
    return {
        "HIGH": "danger",
        "MEDIUM": "warning",
        "LOW": "safe",
    }.get(level, "neutral")


def _render_cards(context: dict) -> str:
    delta = context["delta"]
    risk = context["risk"]
    active_items = context["active_items"]
    course_count = len(risk.get("course_risks", {}))
    escalation_total = int(delta.get("counts", {}).get("escalated", 0)) + int(
        delta.get("counts", {}).get("became_missing", 0)
    )

    cards = [
        ("Courses", str(course_count), "neutral"),
        ("Active Items", str(len(active_items)), "neutral"),
        ("New Changes", str(delta.get("counts", {}).get("new", 0)), "safe"),
        ("Escalations", str(escalation_total), "warning"),
        ("Missing", str(risk.get("missing_count", 0)), _tone_for_risk(str(risk.get("missing_risk", "UNKNOWN")))),
        ("Overall Risk", str(risk.get("overall", "UNKNOWN")), _tone_for_risk(str(risk.get("overall", "UNKNOWN")))),
    ]

    return "\n".join(
        (
            '<section class="cards">',
            *[
                (
                    f'<article class="card tone-{tone}">'
                    f'<div class="card-label">{escape(label)}</div>'
                    f'<div class="card-value">{escape(value)}</div>'
                    "</article>"
                )
                for label, value, tone in cards
            ],
            "</section>",
        )
    )


def _render_course_risks(context: dict) -> str:
    course_risks = context["risk"].get("course_risks", {})
    rows = []
    for course_name, level in sorted(course_risks.items()):
        tone = _tone_for_risk(str(level))
        rows.append(
            f'<li class="pill tone-{tone}"><span>{escape(course_name)}</span><strong>{escape(str(level))}</strong></li>'
        )
    return "\n".join((
        '<section class="panel">',
        "<h2>Course Risk</h2>",
        '<ul class="pill-list">' + ("".join(rows) or "<li class=\"empty\">No course data.</li>") + "</ul>",
        "</section>",
    ))


def _render_today(context: dict) -> str:
    sections: list[str] = [
        '<section class="panel panel-priority">',
        "<h2>Today</h2>",
        '<p class="panel-copy">Start at the top and stop when the board goes quiet.</p>',
    ]
    today_sections = context.get("today_sections", [])
    if not today_sections:
        sections.append('<p class="empty">No active assignments.</p>')
        sections.append("</section>")
        return "\n".join(sections)

    for section in today_sections:
        items = section["items"]
        sections.append('<div class="today-block">')
        sections.append(
            f"<div class=\"today-head\"><h3>{escape(section['title'])}</h3>"
            f"<span class=\"today-count\">{len(items)}</span></div>"
        )
        sections.append(f"<p class=\"today-copy\">{escape(section['description'])}</p>")
        if not items:
            sections.append('<p class="empty">Clear.</p>')
            sections.append("</div>")
            continue
        sections.append('<ul class="today-list">')
        for item in items:
            sections.append(
                "<li class=\"today-item\">"
                "<div>"
                f"<strong>{escape(str(item.get('name') or ''))}</strong>"
                f"<span>{escape(str(item.get('course') or ''))}</span>"
                "</div>"
                "<div>"
                f"<strong>{escape(_format_due_badge(item))}</strong>"
                f"<span>{escape(str(item.get('status') or ''))}</span>"
                "</div>"
                "</li>"
            )
        sections.append("</ul>")
        sections.append("</div>")
    sections.append("</section>")
    return "\n".join(sections)


def _render_changes(context: dict) -> str:
    order = [
        ("new", "New"),
        ("reactivated", "Reactivated"),
        ("became_missing", "Became Missing"),
        ("escalated", "Escalated"),
        ("de_escalated", "De-escalated"),
        ("cleared", "Cleared"),
    ]
    sections: list[str] = ['<section class="panel"><h2>Change Feed</h2>']
    buckets = context["change_buckets"]
    for change_type, title in order:
        items = buckets.get(change_type, [])
        sections.append(f"<h3>{escape(title)}</h3>")
        if not items:
            sections.append('<p class="empty">None.</p>')
            continue
        sections.append(
            "<div class=\"table-shell\"><table><thead><tr>"
            "<th>Due</th><th>Course</th><th>Assignment</th><th>Transition</th>"
            "</tr></thead><tbody>"
        )
        for item in items:
            due_text = str(item.get("to_due_at") or item.get("from_due_at") or "")[:10] or "NO-DUE-DATE"
            deadline_note = ""
            if item.get("deadline_change"):
                deadline_note = f"<br><span class=\"empty\">{escape(str(item.get('deadline_change') or ''))}</span>"
            transition = (
                f"{escape(str(item.get('from_status') or 'absent'))}"
                f" → {escape(str(item.get('to_status') or ''))}"
                f"{deadline_note}"
            )
            sections.append(
                "<tr>"
                f"<td>{escape(due_text)}</td>"
                f"<td>{escape(str(item.get('course') or ''))}</td>"
                f"<td>{escape(str(item.get('name') or ''))}</td>"
                f"<td>{transition}</td>"
                "</tr>"
            )
        sections.append("</tbody></table></div>")
    sections.append("</section>")
    return "\n".join(sections)


def _render_active_items(context: dict) -> str:
    rows = []
    for item in context["active_items"]:
        severity_label = str(item.get("severity_label") or item.get("confidence") or "")
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('date') or ''))}</td>"
            f"<td>{escape(str(item.get('course') or ''))}</td>"
            f"<td>{escape(str(item.get('name') or ''))}</td>"
            f"<td>{escape(str(item.get('status') or ''))}</td>"
            f"<td>{escape(severity_label)}</td>"
            "</tr>"
        )
    return "\n".join((
        '<section class="panel">',
        "<h2>Active Ledger</h2>",
        (
            "<div class=\"table-shell\"><table><thead><tr>"
            "<th>Date</th><th>Course</th><th>Assignment</th><th>Status</th><th>Severity</th>"
            "</tr></thead><tbody>"
        ),
        "".join(rows) or '<tr><td colspan="5" class="empty">No active assignments.</td></tr>',
        "</tbody></table></div>",
        "</section>",
    ))


def render_report_html(context: dict) -> str:
    pulled_at = escape(str(context["pulled_at"]))
    overall_risk = escape(str(context["risk"].get("overall", "UNKNOWN")))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DueCheck Report</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --paper: #fffdf9;
      --ink: #1e1b18;
      --muted: #6e6258;
      --line: #d8cfc3;
      --safe: #245b4a;
      --warning: #a44c1a;
      --danger: #8f2430;
      --neutral: #39556f;
      --shadow: 0 18px 50px rgba(42, 34, 25, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(164, 76, 26, 0.10), transparent 32%),
        linear-gradient(180deg, #f7f1e8 0%, var(--bg) 100%);
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 40px 20px 64px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(251, 245, 237, 0.92));
      border: 1px solid rgba(216, 207, 195, 0.8);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted);
      font-size: 12px;
      margin: 0 0 10px;
    }}
    h1 {{ margin: 0; font-size: clamp(34px, 5vw, 56px); line-height: 0.96; }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
      color: var(--muted);
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 14px;
      margin: 24px 0;
    }}
    .card, .panel {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
    }}
    .card {{ padding: 18px; min-height: 120px; }}
    .card-label {{ font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }}
    .card-value {{ margin-top: 18px; font-size: 30px; font-weight: 700; }}
    .tone-safe {{ border-color: rgba(36, 91, 74, 0.28); }}
    .tone-warning {{ border-color: rgba(164, 76, 26, 0.32); }}
    .tone-danger {{ border-color: rgba(143, 36, 48, 0.32); }}
    .layout {{
      display: grid;
      grid-template-columns: 1.05fr 1.55fr;
      gap: 18px;
      align-items: start;
    }}
    .stack {{ display: grid; gap: 18px; }}
    .panel {{ padding: 22px; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    h3 {{
      margin: 18px 0 10px;
      font-size: 14px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .pill-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }}
    .pill {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.7);
      border: 1px solid var(--line);
    }}
    .panel-copy {{
      margin: 0 0 18px;
      color: var(--muted);
      max-width: 44ch;
    }}
    .today-block + .today-block {{
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid rgba(216, 207, 195, 0.72);
    }}
    .today-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    .today-count {{
      min-width: 36px;
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-family: "SFMono-Regular", "Menlo", monospace;
      font-size: 12px;
      text-align: center;
      color: var(--muted);
      background: rgba(255,255,255,0.7);
    }}
    .today-copy {{
      margin: 8px 0 12px;
      color: var(--muted);
      font-size: 14px;
    }}
    .today-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }}
    .today-item {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
    }}
    .today-item div {{
      display: grid;
      gap: 4px;
    }}
    .today-item span {{
      color: var(--muted);
      font-size: 13px;
    }}
    .table-shell {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,0.72);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-family: "SFMono-Regular", "Menlo", monospace;
      font-size: 13px;
    }}
    th, td {{ padding: 11px 12px; text-align: left; border-bottom: 1px solid rgba(216, 207, 195, 0.72); }}
    thead th {{
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      background: rgba(250, 244, 236, 0.9);
    }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <p class="eyebrow">DueCheck Local Report</p>
      <h1>What changed since your last check.</h1>
      <div class="hero-meta">
        <span>Pulled: {pulled_at}</span>
        <span>Overall risk: {overall_risk}</span>
      </div>
    </section>
    {_render_today(context)}
    {_render_cards(context)}
    <section class="layout">
      <div class="stack">
        {_render_course_risks(context)}
      </div>
      <div class="stack">
        {_render_changes(context)}
        {_render_active_items(context)}
      </div>
    </section>
  </main>
</body>
</html>
"""


def write_report_html(out_dir: Path, output_path: Path | None = None) -> Path:
    context = load_report_context(out_dir)
    target = output_path if output_path is not None else out_dir / "report.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report_html(context))
    return target
