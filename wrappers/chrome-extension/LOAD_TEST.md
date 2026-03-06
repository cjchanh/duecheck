# DueCheck Chrome Extension Live Fetch + Change Detection — Manual Load Test

## Load Path

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `wrappers/chrome-extension`
5. Confirm the extension loads without manifest errors

## Runtime Checklist

1. Open the popup
2. Confirm the first state is `no-credentials`
3. Enter:
   - a Canvas base URL like `https://canvas.example.edu`
   - a valid Canvas access token
4. Click `Save And Sync`
5. Confirm a host-permission prompt appears for the entered Canvas origin
6. If permission is denied:
   - the popup shows a clear permission error
   - no sync proceeds
7. If permission is granted:
   - sync runs immediately
   - popup transitions to `loading`, `ready`, `empty`, or `stale-with-error`
   - `What Changed` renders either real change items or the explicit no-changes message
8. Confirm `chrome.storage.local.get(null)` in the service worker console shows:
   - `settings`
   - `activeCourseCount`
   - `assignments`
   - `changes`
   - `changeCounts`
   - `syncError`
   - `lastAttemptAt`
   - `lastSuccessAt`
9. Reopen the popup and confirm:
   - token field is empty
   - base URL remains populated
10. Close and reopen Chrome
11. Confirm the background service worker restores the `duecheck-sync` alarm on startup
12. While assignments are visible, click `Change Connection`
13. Replace the saved token with a bad token
14. Click `Save And Sync`
15. Confirm:
    - old assignments remain visible
    - an error banner appears
    - `Last sync` remains the previous successful time
    - `Last attempt` updates
    - `What Changed` stays populated from the last successful snapshot

## Scope Truth

This phase verifies live upcoming-assignment fetch plus upcoming-assignment change detection.

Deferred:

- missing-work parity
- risk scoring parity
- IndexedDB run history
- Canvas DOM injection
