# Hero Asset Tooling Gate

## Repo

`<repo>`

## Gate Result

No supported capture tooling was available in this environment for autonomous hero-asset generation.

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

- Create `docs/assets/`
- Wire README hero asset slots to the intended paths
- Add capture template/notes
- Defer real screenshot and GIF generation in `STATE_REPORT.md`
