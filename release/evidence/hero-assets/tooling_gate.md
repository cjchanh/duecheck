# Hero Asset Tooling Gate

## Repo

`/Users/cj/Workspace/active/campus-signal/duecheck`

## Gate Result

Initial gate result: no supported capture tooling was available in this environment for autonomous hero-asset generation.
Follow-up result: the explicit install block was run, `vhs` and Playwright became available, and the real hero assets were captured. See `capture_notes.md`.

## Commands

```bash
which vhs || true
which playwright || true
which asciinema || true
python3 - <<'PY'
import importlib.util
print("playwright_py", bool(importlib.util.find_spec("playwright")))
PY
./.venv/bin/python - <<'PY'
import importlib.util
print("venv_playwright_py", bool(importlib.util.find_spec("playwright")))
PY
```

## Observed Output

```text
playwright_py False
venv_playwright_py False
```

`which vhs`, `which playwright`, and `which asciinema` returned no paths.

## Batch Decision

- Initial pass:
  - create `docs/assets/`
  - wire README hero asset slots to the intended paths
  - add capture template/notes
  - defer real screenshot and GIF generation in `STATE_REPORT.md`
- Follow-up pass after tool install:
  - generate `docs/assets/report-demo.png`
  - generate `docs/assets/demo-flow.gif`
  - replace README placeholders with real media
