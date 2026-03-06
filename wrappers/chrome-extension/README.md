# DueCheck Chrome Extension Shell

This is the first wrapper move, not the finished browser product.

Current state:

- loadable MV3 popup shell
- seeded from the real DueCheck demo artifact bundle
- same Today board, change feed, and course-risk language as the local report
- no external dependencies

How to load it:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `wrappers/chrome-extension`
5. Click the DueCheck extension icon

What it does now:

- loads a bundled demo artifact set into extension storage on install
- renders a click-open popup that mirrors the DueCheck report summary

What it does not do yet:

- sync real Canvas data
- persist run history in IndexedDB
- inject UI into Canvas pages
- ship Chrome Web Store-ready privacy/permission copy

Next strike:

- add the Canvas fetch pipeline in the background service worker
- store normalized snapshots locally
- compute real refresh results from live data instead of demo fixtures
