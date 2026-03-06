# Contributing to DueCheck

DueCheck is a deterministic Canvas sync engine. Keep changes small, testable, and local-first.

## Before You Start

- Open an issue before large changes.
- Avoid adding runtime dependencies unless the change cannot be done with the standard library.
- Do not add school-specific hardcoding.
- Keep the core engine read-only with respect to the LMS.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
ruff check .
```

## Change Rules

- Keep the `LMSAdapter` abstraction narrow.
- Prefer explicit data contracts over hidden side effects.
- Preserve deterministic output ordering.
- Add or update tests for every behavior change.
- Update docs and sample output when user-visible behavior changes.

## Pull Requests

- Explain the behavior change in plain language.
- List validation steps you ran.
- Call out any schema, CLI, or artifact format changes.
- Keep unrelated cleanup out of the same PR.

## Good First Contributions

- Test coverage for adapter edge cases
- Docs improvements for setup and troubleshooting
- Output/reporting polish that keeps artifacts deterministic
- Additional rule-based risk checks with tests
