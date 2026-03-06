# DueCheck State Report

## Current Status

- Engine-spec hardening remains landed and green.
- Release-surface blockers are fixed locally and validated against a built wheel.
- CLI UX surface for `init`, `doctor`, and `redact` is implemented locally and validated.
- Scheduling surface for passive daily use is implemented and now verified against real `launchd`.
- Hero asset batch completed with real screenshot and GIF captures.
- Extension-wrapper phase 0 shell is landed in-repo.
- Public release completed:
  - GitHub `main` pushed
  - public README media render verified
  - tag `v0.2.0` pushed
  - PyPI publish completed

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
- Public release status: `LIVE`
- GitHub repo: `https://github.com/cjchanh/duecheck`
- PyPI package: `https://pypi.org/project/duecheck/0.2.0/`
- Release workflow fix landed:
  - `e90bc37` — `ci(release): fix download-artifact pin`

## CLI UX Surface Status

- CLI UX commits landed:
  - `464725a` — `feat(cli): add config resolution, init, doctor, and redact`
  - `dbe1509` — `docs: document init, doctor, redact, and config precedence`
- Token-in-config implemented: `yes`
  - `duecheck init` can save `canvas_token` when the user explicitly confirms or passes `--yes` with `--canvas-token`
  - stored tokens remain plaintext on disk by design
- Config precedence:
  - `CLI > env > config > hard default`
- `redact` report regeneration working: `yes`
  - `duecheck redact` now writes `ledger.json`, `delta.json`, `risk.json`, `changes.md`, `pulled_at.txt`, and `report.html`
  - the redacted bundle validates with `duecheck verify`
  - the redacted bundle re-renders with `duecheck report --html`
- Final test count before scheduling: `102`

## CLI UX Batch Notes

- Added `duecheck/config.py` for config discovery, JSON persistence, and runtime resolution.
- Added `duecheck init` for local default setup without repeated flag entry.
- Added `duecheck doctor` for local config, token-source, asset, output-dir, and artifact diagnostics.
- Added `duecheck redact` for deterministic redacted bug-report bundles.
- Preserved engine computation contracts; this change only widened CLI UX and redaction support around the hardened engine.

## Scheduling Surface Status

- Scheduling commit landed:
  - `3efb959` — `feat(cli): add macOS-first schedule surface`
- Scheduling is now macOS-first through `duecheck schedule install|status|remove`.
- The schedule installs a LaunchAgent plus a local runner script that reuses the existing pull and report flows.
- Token handling:
  - preferred: config-stored token
  - fallback: embed the currently resolved token in the private runner script when install cannot rely on shell env inheritance
- Engine computation contracts remain unchanged; scheduling wraps the hardened CLI surface.
- Verification:
  - `python3 -m pytest -q` → `107 passed`
  - `./.venv/bin/ruff check .` → `All checks passed!`
  - `python3 -m duecheck.cli schedule --help` → passed
  - `python3 -m duecheck.cli schedule install --help` → passed
  - verification artifacts: `release/evidence/schedule-surface/`
  - real `launchd` smoke pass: passed
    - installed LaunchAgent into the real `gui/<uid>` domain with isolated repo-local `HOME`/`XDG_CONFIG_HOME`
    - `launchctl print gui/<uid>/io.duecheck.sync` reported the agent as loaded and running after `kickstart`
    - controlled runner used `http://127.0.0.1:9` so execution could fail fast without touching real Canvas data
    - `duecheck schedule remove` removed the plist and runner script cleanly afterward
    - smoke evidence: `release/evidence/schedule-surface/launchd-smoke/20260306T092756Z/`

## Extension Wrapper Phase 0 Status

- Extension shell landed in-repo at `wrappers/chrome-extension/`
- Current scope:
  - MV3 popup shell
  - background seeding of the real demo artifact bundle into extension storage
  - same Today board, change feed, and course-risk language as the local report
  - no external JavaScript dependencies
- Verification:
  - `node --test wrappers/chrome-extension/test/view-model.test.mjs` → passes
  - the popup view-model is driven by the real artifact bundle shape, not a mock-only schema
- Honest state:
  - wrapper shell: implemented+tested for local module logic
  - browser runtime load in Chrome: designed/unverified
  - real Canvas sync pipeline: designed/unverified
  - IndexedDB run history: designed/unverified

## Hero Asset Gate Status

- Hero asset paths landed: `docs/assets/report-demo.png`, `docs/assets/demo-flow.gif`
- README placement above the first code block: `yes`
- Capture template added: `docs/assets/CAPTURE_TEMPLATE.md`
- Capture notes added: `release/evidence/hero-assets/capture_notes.md`
- Capture toolchain used:
  - `vhs` for `docs/assets/demo-flow.gif`
  - Python Playwright for `docs/assets/report-demo.png`
- Batch result: complete
  - asset wiring landed
  - real screenshot landed
  - real GIF landed
  - README now renders real media instead of placeholder slots

## Deferred

- Extension Canvas sync pipeline
  Deferred. The current shell is seeded from the real demo artifact bundle, but it does not yet fetch live Canvas data.
- Extension persistence and injection
  Deferred. IndexedDB run history, Canvas DOM injection, and store-ready privacy/permission hardening remain separate work items.

## Next Planned Work

- Extension wrapper live-data phase
  - add Canvas fetch pipeline in the background service worker
  - normalize live data into the current Today/change/risk view model
  - keep browser/runtime concerns out of the Python engine contract
- Real-user evidence loop
  - use `doctor` and `redact` to collect reproducible bug reports and real usage signal before widening scope
- Linux scheduling parity
  - add a user-level timer path after the macOS surface settles

## Active Invariants Held

***REMOVED***
***REMOVED***
***REMOVED***
***REMOVED***

