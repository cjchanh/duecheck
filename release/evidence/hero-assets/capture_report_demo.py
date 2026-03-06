from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: capture_report_demo.py REPORT_HTML OUTPUT_PNG", file=sys.stderr)
        return 2

    report_html = Path(sys.argv[1]).resolve()
    output_png = Path(sys.argv[2]).resolve()
    if not report_html.exists():
        print(f"missing report html: {report_html}", file=sys.stderr)
        return 1

    output_png.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1600}, device_scale_factor=2)
        page.goto(report_html.as_uri(), wait_until="load")
        page.wait_for_timeout(600)
        page.screenshot(path=str(output_png))
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
