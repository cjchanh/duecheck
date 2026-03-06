# DueCheck

DueCheck tells you what changed in Canvas since your last check.

- See new deadlines, missing work, and escalations without re-reading every course page.
- Keep a local assignment ledger and compare today against the last good snapshot.
- Generate a static report you can open in a browser with no hosted service and no runtime dependencies.

<!-- TODO: add screenshot of report.html from duecheck demo -->

## Quick Start

### After v0.2.0 is published

```bash
pip install duecheck
duecheck demo --out-dir ./demo --open
```

### From source / development

```bash
git clone https://github.com/cjchanh/duecheck.git
cd duecheck
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
duecheck demo --out-dir ./demo --open
```

## Demo Flow

No Canvas account needed:

```bash
duecheck demo --out-dir ./demo --open
duecheck verify --out-dir ./demo --json
duecheck report --html --out-dir ./demo --open
```

## What It Produces

- `report.html` — self-contained local report with a Today board, change feed, and ledger table
- `ledger.json` — persistent assignment ledger with typed artifact metadata
- `delta.json` — structured diff between the current run and the previous ledger state
- `changes.md` — markdown changelog generated from the delta
- `risk.json` — rule-based academic risk summary
- `runs/` — immutable per-run snapshots used for history and repair

## Example Output

```markdown
# Assignment Changes
_Pulled: 2026-03-05T12:00:00Z_

## Summary
- new: 1
- became_missing: 1
- escalated: 1
- deadline_moved_later: 1
```

## Canvas Quickstart

Get a Canvas API token from: Canvas > Settings > Approved Integrations > New Access Token.

```bash
export CANVAS_TOKEN="your-token-here"
duecheck --canvas-url https://canvas.yourschool.edu --out-dir ./my-classes
```

## CLI Reference

```text
duecheck --canvas-url URL --out-dir DIR [options]

Core options:
  --token-env VAR           Env var with Canvas token (default: CANVAS_TOKEN)
  --course-filter COURSE    Filter to specific courses
  --grade-threshold N       Risk threshold (default: 80.0)
  --repair                  Rebuild delta from existing ledger
  --fail-on TOKEN           Exit 2 on HIGH|MEDIUM|escalated|missing
  --json                    Output summary as JSON

Extra commands:
  duecheck demo --out-dir DIR [--json] [--open]
  duecheck verify --out-dir DIR [--json]
  duecheck report --html --out-dir DIR [--output PATH] [--json] [--open]
```

## Technical Notes

DueCheck is a stdlib-only Python engine for Canvas assignment tracking. It:

1. Pulls courses, assignments, and missing submissions from Canvas.
2. Builds a typed ledger of assignment state with `schema_version`, `engine_version`, and `source_adapter`.
3. Computes a structured delta with change types like `new`, `became_missing`, `escalated`, `cleared`, and additive deadline movement annotations.
4. Scores academic risk with deterministic rules instead of heuristics or AI.
5. Validates artifacts before writing them, then writes through temp files plus atomic replace.

Backward compatibility is preserved for older artifacts through migration shims:

- legacy `confidence` still loads
- produced artifacts write only `severity_label`
- import paths from `duecheck.__init__` stay stable

## Schemas

Machine-readable schemas ship inside the package at [`duecheck/schemas/`](duecheck/schemas/):

- [`duecheck/schemas/ledger.schema.json`](duecheck/schemas/ledger.schema.json)
- [`duecheck/schemas/delta.schema.json`](duecheck/schemas/delta.schema.json)
- [`duecheck/schemas/risk.schema.json`](duecheck/schemas/risk.schema.json)

`duecheck verify` uses a matching stdlib-only structural validator against the same artifact contract.

## Architecture

```text
duecheck/
  adapter.py        Canvas adapter
  cli.py            CLI entrypoint
  delta.py          Delta computation
  ledger.py         Ledger build and migration
  renderers/        Markdown and HTML rendering
  risk.py           Rule-based risk scoring
  schemas/          Packaged JSON Schemas
  types.py          Shared types and artifact models
  validate.py       Stdlib artifact validation
```

## Development

```bash
pytest -q
ruff check .
python3 -m build
twine check dist/*
```

## Community

- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

## License

MIT. See [LICENSE](LICENSE).
