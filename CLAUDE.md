# DueCheck — Project Rules

## What This Is

Open-source Canvas assignment tracking engine. Python 3.10+. No external API dependencies for core functionality.

## Architecture

- `duecheck/types.py` — shared types, `LMSAdapter` protocol, constants
- `duecheck/adapter.py` — `CanvasAdapter` (Canvas LMS integration)
- `duecheck/ledger.py` — persistent assignment ledger
- `duecheck/delta.py` — delta computation between sync runs
- `duecheck/risk.py` — rule-based academic risk scoring
- `duecheck/cli.py` — CLI entrypoint

## Hard Rules

1. No school-specific hardcoding. All school-specific values must be parameterized.
2. No external AI/LLM dependencies in core modules. Risk scoring is rule-based.
3. `LMSAdapter` protocol must remain the abstraction boundary for LMS integrations.
4. Tests must pass before any commit: `pytest -q && ruff check .`
5. No new dependencies without justification. The engine uses only stdlib.

## Testing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest ruff
pytest -v
ruff check .
```

## CLI

```bash
duecheck --canvas-url https://canvas.example.com --out-dir ./output
duecheck --repair --out-dir ./output
```
