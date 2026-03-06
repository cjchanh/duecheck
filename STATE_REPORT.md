# DueCheck State Report

## Current Status

- Engine-spec hardening remains landed and green.
- Release-surface blockers are fixed locally and validated against a built wheel.
- Release readiness: `READY TO PUSH+TAG`

## Release-Surface Commits Landed

- `31f4069` — `refactor(packaging): relocate schemas into package and include in wheel`
- `ca9d435` — `feat(report): add Today section and --open support`
- `7e62bc9` — `docs: rewrite README for student-first release surface`
- `0f77e0f` — `ci(release): add pinned release workflow and smoke gate`

## What This Batch Fixed

- Relocated schemas from repo-root `schemas/` into `duecheck/schemas/`.
- Updated packaging so built wheels include both `duecheck/demo_data/*.json` and `duecheck/schemas/*.json`.
- Added package-resource coverage for demo data and schemas.
- Polished the HTML report with a student-facing `Today` board:
  - `Overdue`
  - `Due In 48 Hours`
  - `Due This Week`
- Added opt-in `--open` support to `duecheck demo` and `duecheck report` using stdlib `webbrowser`.
- Rewrote `README.md` to lead with student value, dual quickstarts, demo flow, artifact list, CLI reference, and packaged schema paths.
- Added `.github/workflows/release.yml` with pinned SHAs for build, wheel smoke, and trusted PyPI publish readiness.

## Verification

- Tests: `80` → `85`
- `python3 -m pytest -q` → `85 passed`
- `./.venv/bin/ruff check .` → `All checks passed!`
- `python3 -m build` → passed
- `twine check dist/*` → passed
- Fresh-venv wheel smoke:
  - `duecheck --help` → passed
  - `duecheck demo --out-dir TMP --json` → passed
  - `duecheck verify --out-dir TMP --json` → passed
  - `duecheck report --html --out-dir TMP` → passed
- Installed package resources verified through `importlib.resources`:
  - `duecheck/demo_data/sample_bundle.json` present
  - `duecheck/schemas/ledger.schema.json` present
- Import compatibility check passed:
  - `render_delta_markdown`
  - `render_report_html`
  - `load_report_context`
  - `build_delta`
  - `build_ledger`
  - `compute_overall_risk`
  - `AssignmentObservation`

## Release Surface Status

- Schemas relocated: `yes`
- `--open` landed: `yes`
- Local wheel smoke test passed: `yes`
- Repo state target: clean after final docs closeout
- Release readiness: `READY TO PUSH+TAG`

## Deferred

- Real README screenshot asset
  Deferred. The README now has the required placeholder comment; the actual image capture can be added as a follow-up docs pass.
- Push/tag execution
  Deferred by explicit session boundary. This run stops at local release readiness and does not push or tag.

## Active Invariants Held

- Tuesday Bar
- Fail-Closed
- Signal Over Noise
- State Before Loop
- Constraints Over Plasticity
