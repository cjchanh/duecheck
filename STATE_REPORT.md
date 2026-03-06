# DueCheck State Report

## Current Status

- Engine hardening landed and green.
- Release blockers fixed locally and validated against a built wheel.
- CLI UX surface for `init`, `doctor`, and `redact` is implemented and validated.
- Scheduling surface for passive daily use is implemented and verified against real `launchd`.
- Hero assets completed with real screenshot and GIF captures.
- Extension live-fetch phase 1 is landed in-repo.
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

## Extension Live Fetch Phase 1

- Live-fetch wrapper landed at `wrappers/chrome-extension/`
- MV3 popup shell with:
  - Canvas API client for active courses + upcoming assignments
  - pagination via Canvas `Link` headers
  - background hourly sync alarm plus popup `Sync Now`
  - fail-closed dynamic host permissions
  - stale-data preservation on sync failure
  - popup states:
    - `no-credentials`
    - `loading`
    - `empty`
    - `ready`
    - `stale-with-error`
    - `error-no-data`
- No external JavaScript dependencies
- Commits landed:
  - `cf5db67` — `feat(extension): Canvas API client with pagination and validation`
  - `780ca18` — `feat(extension): background sync with alarms, sync-now, graceful failure`
  - `dd2eb00` — `feat(extension): popup states, security, and dynamic host permissions`
- Honest state:
  - local module logic: implemented+tested
  - browser runtime load in Chrome: designed/unverified
  - live upcoming-assignment fetch: implemented+tested at module level
  - DueCheck parity features in extension: designed/unverified
  - IndexedDB run history: designed/unverified

Test baseline → final count:

- Python: `107 -> 107`
- Node: `3 -> 24`

Findings resolved:

- Canvas pagination is now required for both course and assignment endpoints
- popup save path requests host permission dynamically per Canvas origin
- sync failure preserves the last good assignment list
- popup security path never logs or re-renders the saved token
- scope is explicit: live fetch only, not extension-side parity

Storage key contract:

- `settings`
- `assignments`
- `syncError`
- `lastAttemptAt`
- `lastSuccessAt`

## Hero Assets

- `docs/assets/report-demo.png`, `docs/assets/demo-flow.gif`
- README renders real media above the fold

## Deferred

- Phase 1.5: missing-work endpoint and `became_missing` classification
- Phase 2: snapshot diffing (`lastSnapshot` vs `currentSnapshot`)
- Phase 3: risk scoring parity with Python engine
- Phase 4: IndexedDB run history
- Chrome runtime load verification per `wrappers/chrome-extension/LOAD_TEST.md`
- Extension persistence and injection (Canvas DOM injection, store-ready hardening)

## Next Planned Work

- Extension runtime verification and parity hardening
- Real-user evidence loop via `doctor` and `redact`
- Linux scheduling parity

## Active Invariants Held

- Tuesday Bar
- Fail-Closed
- Constraints Over Plasticity
- Signal Over Noise
- State Before Loop
