# DueCheck State Report

## Current Status

- Engine hardening landed and green.
- Release blockers fixed locally and validated against a built wheel.
- CLI UX surface for `init`, `doctor`, and `redact` is implemented and validated.
- Scheduling surface for passive daily use is implemented and verified against real `launchd`.
- Hero assets completed with real screenshot and GIF captures.
- Extension-wrapper phase 0 shell is landed in-repo.
- Public release completed:
  - GitHub `main` pushed
  - public README media render verified
  - tag `v0.2.0` pushed
  - PyPI publish completed

## What Changed

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

- Tests: `107 passed`
- `python3 -m pytest -q` passed
- `ruff check .` passed
- `python3 -m build` passed
- `twine check dist/*` passed
- Fresh-venv wheel smoke passed
- Installed package resources verified through `importlib.resources`
- Import compatibility check passed

## Release Status

- Schemas relocated: `yes`
- `--open` landed: `yes`
- Local wheel smoke test passed: `yes`
- Public release status: `LIVE`
- GitHub repo: `https://github.com/cjchanh/duecheck`
- PyPI package: `https://pypi.org/project/duecheck/0.2.0/`

## CLI UX Status

- Token-in-config implemented: `yes`
- Config precedence: `CLI > env > config > hard default`
- `redact` report regeneration working: `yes`

## Scheduling Status

- macOS-first through `duecheck schedule install|status|remove`
- LaunchAgent plus local runner script that reuses existing pull and report flows
- Real `launchd` smoke test passed

## Extension Wrapper Phase 0

- Extension shell landed at `wrappers/chrome-extension/`
- MV3 popup shell with background seeding of real demo artifact bundle
- Same Today board, change feed, and course-risk language as the local report
- No external JavaScript dependencies
- Honest state:
  - wrapper shell: implemented+tested for local module logic
  - browser runtime load in Chrome: designed/unverified
  - real Canvas sync pipeline: designed/unverified
  - IndexedDB run history: designed/unverified

## Hero Assets

- `docs/assets/report-demo.png`, `docs/assets/demo-flow.gif`
- README renders real media above the fold

## Deferred

- Extension Canvas sync pipeline
- Extension persistence and injection (IndexedDB, Canvas DOM injection, store-ready hardening)

## Next Planned Work

- Extension wrapper live-data implementation
- Real-user evidence loop via `doctor` and `redact`
- Linux scheduling parity
