# DueCheck

**Know what changed. Handle what matters.**

DueCheck is an open-source assignment tracking engine for college students. It syncs with Canvas, keeps a persistent ledger of every assignment, and tells you exactly what changed since yesterday.

## The Problem

Canvas shows you a dashboard of everything but tells you nothing about what *changed*. You have four classes, thirty assignments, and a page that looks the same every time you open it. A new deadline appeared, a grade dropped, a missing submission is silently getting worse — but you would not know unless you checked every course, every day.

Most students do not check every course every day.

## What DueCheck Does

Every time you run it, DueCheck:

1. **Pulls** your current assignments, grades, and missing submissions from Canvas
2. **Diffs** them against yesterday's state using a persistent ledger
3. **Classifies** changes: new, escalated, de-escalated, cleared, unchanged
4. **Scores** academic risk based on grades, missing work, and overdue items
5. **Outputs** a clean summary of what needs your attention

The output is deterministic. No AI, no chatbot, no "study coach." Just structured state tracking with diffs.

## Quick Start

```bash
pip install duecheck
```

Get a Canvas API token: Canvas > Settings > Approved Integrations > New Access Token.

```bash
export CANVAS_TOKEN="your-token-here"
duecheck --canvas-url https://canvas.yourschool.edu --out-dir ./my-classes
```

Output files:
- `ledger.json` — full assignment ledger with status, dates, and confidence
- `delta.json` — structured diff: what changed since last run
- `changes.md` — human-readable changelog
- `risk.json` — academic risk assessment

## Example Output

### Changes (changes.md)

```markdown
# Assignment Changes
_Pulled: 2026-03-05T12:00:00Z_

## Summary
- new: 2
- escalated: 1
- cleared: 1
- unchanged_active: 5

## New Items
- 2026-03-10 | English Composition | Essay 3 Draft | absent -> due_7d

## Escalated Items
- 2026-03-06 | Philosophy | Reflection Paper 4 | due_7d -> due_48h
```

### Risk (risk.json)

```json
{
  "overall": "MEDIUM",
  "course_risks": {
    "English Composition": "LOW",
    "Philosophy": "MEDIUM"
  },
  "missing_risk": "LOW",
  "flagged_courses": ["Philosophy"],
  "missing_count": 0
}
```

## CLI Reference

```
duecheck --help

Options:
  --canvas-url URL          Canvas base URL (or set CANVAS_URL env var)
  --token-env VAR           Env var with Canvas token (default: CANVAS_TOKEN)
  --out-dir DIR             Output directory (default: current dir)
  --course-filter COURSE    Filter to specific courses (e.g. "ENGL 1308")
  --grade-threshold N       Risk threshold (default: 80.0)
  --repair                  Rebuild delta from existing ledger
  --json                    Output summary as JSON
```

## How It Works

DueCheck maintains a **persistent assignment ledger** — a JSON file that tracks every assignment it has ever seen, with:

- `status`: `missing`, `due_48h`, `due_7d`, or `not_observed`
- `first_seen` / `last_seen`: when the assignment entered and last appeared in a sync
- `confidence`: `high` (missing/due_48h), `medium` (due_7d), `low` (not_observed)
- `item_id`: deterministic hash of course + assignment name

Each run compares the current state to the previous ledger and classifies every assignment into one of:

| Change Type | Meaning |
|---|---|
| `new` | First time seeing this assignment |
| `escalated` | Status got worse (e.g. `due_7d` -> `missing`) |
| `de_escalated` | Status improved |
| `reactivated` | Was `not_observed`, now active again |
| `cleared` | Was active, now `not_observed` |
| `unchanged_active` | Still active, same status |
| `unchanged_inactive` | Still inactive |

## Architecture

```
duecheck/
  types.py      Shared types, LMSAdapter protocol, constants
  adapter.py    CanvasAdapter (LMS integration)
  ledger.py     Persistent ledger: load, merge, build, sort
  delta.py      Delta computation + markdown rendering
  risk.py       Rule-based risk scoring
  cli.py        CLI entrypoint
```

The `LMSAdapter` protocol is designed for future LMS support (Blackboard, Moodle, etc.) without rewriting the core engine.

## Development

```bash
git clone https://github.com/your-username/duecheck
cd duecheck
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).

## Origin

DueCheck started as a personal tool built by a Marine veteran going back to college. Canvas had all the data, but none of the signal. The warning signs were there — they were just invisible in the workflow.

This tool keeps a daily ledger and diffs it. It caught a missing submission that would have cost a letter grade. Then it caught two more.

Now it is open source, so you can run it too.
