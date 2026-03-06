# DueCheck Engine-Spec Hardening — State Report

## Commits Landed

- `c6d1ce6` — `feat(engine): immutable run history, stable LMS identity, dev extras fix`
- `5239bf7` — `feat(cli): add duecheck demo and duecheck report --html`
- `f25809a` — `docs(community): add contributor, security, conduct, issue/PR templates, GitHub hardening`
- `60a764a` — `feat(types): typed artifact models, fail-closed writes, and severity_label contract`
- `465303f` — `refactor(renderers): split markdown and HTML renderers out of engine modules`
- `235504f` — `feat(delta): add became_missing and deadline move annotations`
- `2d458f9` — `test(golden): add replay fixtures and schema validation suite`
- `7bbdc67` — `docs: update README for typed artifacts, verify, and fail-on`

## Test Baseline → Final

- `61` → `80`

## Findings Resolved

- `--repair` now rebuilds from immutable run snapshots instead of diffing `ledger.json` against itself.
- Assignment identity is adapter-backed through `source_key`, with legacy matching preserved for older ledgers.
- Artifacts are stamped with `schema_version`, `engine_version`, and `source_adapter`.
- Canonical artifact writes are fail-closed: payloads validate in memory first, then write through temp files plus atomic replace.
- Output contract renamed from `confidence` to `severity_label`; legacy `confidence` still loads through compatibility shims.
- `duecheck verify` validates `ledger.json`, `delta.json`, and `risk.json` with stdlib-only structural checks.
- Markdown and HTML rendering moved out of engine computation into `duecheck/renderers/`.
- Delta semantics now include `became_missing` plus additive `deadline_moved_earlier` / `deadline_moved_later`.
- Golden fixtures now replay first-run, changed-run, and repair scenarios with schema validation coverage.

## Deferred

- `grade_dropped` / `grade_recovered`
  Deferred. Clean course-level transition tracking needs a dedicated course snapshot contract; inferring it from assignment ledger rows would widen scope and weaken the engine contract.
- Shipping repo-root `schemas/` through package-data
  Deferred. The schemas are published and tested in-repo, but packaging the repo-root directory without duplicating schema sources would widen the package layout in this strike.

## Active Invariants Held

- Tuesday Bar
- Fail-Closed
- Signal Over Noise
- State Before Loop
- Constraints Over Plasticity
