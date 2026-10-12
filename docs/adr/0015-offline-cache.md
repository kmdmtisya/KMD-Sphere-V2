# ADR-0015: Encrypted offline snapshots (DEC-12)

Status: Accepted (proposed in P09-T06, 2026-10-12; chosen by the user on 2026-10-12)

## Context
P09-T06 needs the app to show the last good data when it cannot reach the API, without leaking one user's data to another and without keeping financial data readable on the device. The app has no offline edits: every write goes to the server, which is authoritative.

Options: (1) encrypted per-response snapshots, (2) an encrypted SQL database (Drift with SQLCipher), (3) the platform secure storage alone.

## Decision
1. **Encrypted snapshots.** Each successful API GET is kept as one file: the JSON body and the time it was saved, encrypted with AES-256-GCM (`cryptography`, pure Dart). File names are SHA-256 hashes of the request path and query, so ids and dates are not visible either.
2. **Key custody.** One random 256-bit key, created on first use and kept in the platform secure storage (Keychain / Android Keystore via `flutter_secure_storage`). It never leaves the device and is never logged.
3. **Per user.** Snapshots sit in a folder named by a hash of the signed-in user's subject. Signing out, or the session ending, deletes every snapshot folder and the key, so a new key is made for the next user.
4. **Use.** Only when a GET fails because the device is offline (connection error or timeout) is the snapshot served, and the app shows that it is offline and how old the data is. Any other failure (401, 403, 404, 5xx) is shown as itself, never hidden behind saved data.

## Consequences
- No native database libraries or migrations; snapshots are read-only copies, which is all P09 needs.
- A future offline-edit feature would need a different store (revisit this ADR).
- Lost key (app reinstall, secure-storage reset): snapshots cannot be decrypted and are treated as absent.
