# DueCheck Hero Asset Capture Template

## Intended Asset Paths

- `docs/assets/report-demo.png`
- `docs/assets/demo-flow.gif`

## Capture Tool Gate

Check before recording:

```bash
which vhs || true
which playwright || true
which asciinema || true
python3 - <<'PY'
import importlib.util
print("playwright_py", bool(importlib.util.find_spec("playwright")))
PY
```

Decision rule:

- If `vhs` is available, use it for `docs/assets/demo-flow.gif`
- If Playwright is available, use it for `docs/assets/report-demo.png`
- If both are available, land both assets
- If only one capture path is available, land that asset and defer the other in `STATE_REPORT.md`
- If neither is available, do not bootstrap new global tooling in this batch

## Screenshot Spec

- Source:
  - `python3 -m duecheck.cli demo --out-dir "$tmpdir/demo"`
  - `python3 -m duecheck.cli report --html --out-dir "$tmpdir/demo" --open`
- Capture:
  - browser width about `1440px`
  - zoom `100%`
  - hero + Today section + first metrics visible
  - no devtools, bookmarks bar, or unrelated tabs

## GIF Spec

Preferred deterministic path if `vhs` is available:

- create `demo.tape`
- render to `docs/assets/demo-flow.gif`
- fixed dimensions and theme in the tape file
- record only:
  1. `python3 -m duecheck.cli demo --out-dir ./demo`
  2. `python3 -m duecheck.cli verify --out-dir ./demo --json`
  3. `python3 -m duecheck.cli report --html --out-dir ./demo`

Manual fallback if terminal capture tooling is available:

- terminal size about `120x34`
- single font/theme for the whole recording
- keep total duration under `20s`

## README Placement

Assets belong above the first code block in `README.md` in this order:

1. thesis line
2. screenshot
3. short value bullets
4. GIF
5. first code block

## Capture Notes To Record

- tool used
- terminal font
- terminal theme
- terminal size
- browser width
- browser zoom
- exact command sequence
