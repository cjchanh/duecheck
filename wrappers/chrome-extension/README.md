# DueCheck Chrome Extension Wrapper

This is a live-fetch wrapper phase, not the finished browser product.

Current state:

- loadable MV3 popup shell
- live Canvas fetch for upcoming assignments
- background sync with hourly alarm plus popup `Sync Now`
- local popup states for missing credentials, loading, empty results, ready data, stale data, and error recovery
- no external dependencies

How to load it:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `wrappers/chrome-extension`
5. Click the DueCheck extension icon

What it does now:

- saves a Canvas base URL and token into `chrome.storage.local`
- requests host permission for the entered Canvas origin at save time
- fetches active courses plus upcoming assignments through the Canvas API
- preserves the last good assignment list if a sync fails
- renders a click-open popup for the live upcoming-assignment surface

What it does not do yet:

- classify missing work with Python-engine parity
- compute snapshot diffs or risk scores in the extension
- persist run history in IndexedDB
- inject UI into Canvas pages
- ship Chrome Web Store-ready privacy/permission copy

Security note:

- the Canvas token is stored locally in extension storage
- DueCheck does not encrypt it
- the popup never logs it and never renders it back after save
- saving is overwrite-only

Next strike:

- add missing-work parity
- add snapshot diffing and run history
- harden the browser runtime path for a real store-ready build
