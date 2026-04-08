## Why

Operators managing multiple Codex accounts currently have no built-in way to compare remaining quota across saved snapshots and the current live session. The underlying ChatGPT-backed usage endpoint is available now, so this change adds a first-class usage query workflow instead of forcing manual account switching or ad hoc scripts.

## What Changes

- Add a new `codex-auth usage [name]` command that shows human-friendly 5-hour and weekly quota information.
- Query all managed accounts by default and include the current unmanaged live account when it does not match a saved snapshot.
- Fetch structured usage data from the ChatGPT backend usage endpoint instead of parsing `codex login status`.
- Automatically refresh expired or near-expiry ChatGPT OAuth access tokens during usage queries and persist refreshed credentials back into the relevant local snapshot and current live auth file when applicable.
- Keep the feature non-interactive and focused on terminal-readable output rather than machine-readable export formats.

## Capabilities

### New Capabilities
- `account-usage`: Querying and rendering account quota information for managed snapshots and the current unmanaged live account.

### Modified Capabilities

None.

## Impact

- Adds new behavior in `src/codex_auth/cli.py`, `src/codex_auth/service.py`, `src/codex_auth/store.py`, and new supporting modules for usage API access and token refresh.
- Extends the test suite with usage API, service, and CLI coverage.
- Relies on the existing ChatGPT OAuth snapshot fields already stored in managed accounts and `~/.codex/auth.json`.
- Does not change switching, transfer, or snapshot management behavior outside the new usage command.
