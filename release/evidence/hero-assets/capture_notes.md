# Hero Asset Capture Notes

## Assets

- `docs/assets/report-demo.png`
- `docs/assets/demo-flow.gif`

## Tooling

- GIF: `vhs`
- Screenshot: Python Playwright (`playwright` in `./.venv`)

## Terminal GIF Settings

- tool: `vhs`
- tape: `release/evidence/hero-assets/demo-flow.tape`
- terminal font: `SF Mono`
- terminal theme: `GitHub Dark`
- terminal size: `1600x920`
- window bar: `Colorful`
- typing speed: `35ms`

Commands recorded:

1. `python3 -m duecheck.cli demo --out-dir ./demo`
2. `python3 -m duecheck.cli verify --out-dir ./demo --json`
3. `python3 -m duecheck.cli report --html --out-dir ./demo`

## Report Screenshot Settings

- tool: Python Playwright
- script: `release/evidence/hero-assets/capture_report_demo.py`
- viewport width: `1440`
- viewport height: `1600`
- browser zoom: `100%`
- device scale factor: `2`

Command sequence used to build the source report:

1. `python3 -m duecheck.cli demo --out-dir "$tmpdir/demo"`
2. `python3 -m duecheck.cli report --html --out-dir "$tmpdir/demo"`
3. `./.venv/bin/python release/evidence/hero-assets/capture_report_demo.py "$tmpdir/demo/report.html" docs/assets/report-demo.png`
