# DueCheck — Agent Rules

## For Any AI Agent Working on This Repo

1. Read `CLAUDE.md` first. Those are hard constraints.
2. Run `pytest -q && ruff check .` before proposing any commit.
3. Do not add school-specific hardcoding. No real school names, course codes, or institution identifiers in source.
4. Do not add external dependencies without explicit approval.
5. Do not modify `duecheck/types.py` without understanding downstream impact — it defines the protocol and constants used by every other module.
6. The `LMSAdapter` protocol is intentionally minimal (3 methods). Do not expand it without a concrete use case.
7. Tests must cover new behavior. One test per behavior. No test files without assertions.
