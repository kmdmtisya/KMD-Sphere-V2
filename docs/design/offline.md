# Offline, stale data and errors (P09-T06, ADR-0015)

## What the user sees
- **Online:** live data, as before.
- **Offline with saved data:** every screen that loaded before shows its last good data, and a banner above the tabs says "You're offline. Showing saved data: As of 2 hours ago." (the oldest copy on screen), with **Try again**.
- **Offline with nothing saved:** the screen's own offline error state (P09-T01 `LoadErrorView`), and the banner says some screens have no saved data.
- **Back online:** the first request that reaches the server (or Try again, which checks `/health/live`) clears the banner and reloads every live screen.
- **Errors that are not "offline"** (401, 403, 404, 422, 429, 5xx) are shown as themselves. Saved data never hides them.

## How
- `OfflineInterceptor` (after the auth interceptor in the API client): saves every 2xx JSON GET, and answers a GET that fails for lack of a connection (connection error, timeout, or a token refresh that could not reach sign-in) from the saved copy. Writes are never saved or replayed.
- Connectivity is judged from real requests (`onlineProvider`), not the radio state.
- `EncryptedSnapshotCache`: AES-256-GCM files under the app support folder, one folder per user (hash of the subject), file names hashed from the request, key in secure storage.
- `dataEpochProvider`: bumped on reconnect, sign-in, sign-out and session end. The API client watches it, so every live repository and every provider built on one is rebuilt.

## Sign-out and user change
Signing out, or the session ending, immediately drops everything held in memory (epoch bump) and deletes every saved file and the key in the background. A different user who signs in next cannot read the previous user's files: they sit under another user folder, and the key they were written with is gone.

## Not covered
- Offline edits (every write needs the server).
- Platform radio-state listening (connectivity is inferred from requests; a periodic probe can be added if needed).
