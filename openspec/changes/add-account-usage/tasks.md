## 1. Usage and Refresh Foundations

- [x] 1.1 Add usage data models for rate-limit windows, rendered usage results, and query targets.
- [x] 1.2 Add a token refresh helper that detects near-expiry access tokens and refreshes ChatGPT OAuth credentials with the built-in client ID.
- [x] 1.3 Add a usage API helper that queries the ChatGPT backend usage endpoint and normalizes primary, secondary, and credits data.
- [x] 1.4 Add focused tests for usage payload parsing, token refresh behavior, and HTTP failure handling.

## 2. Service and Storage Integration

- [ ] 2.1 Add store helpers for overwriting refreshed managed snapshots and safely syncing refreshed live auth state.
- [ ] 2.2 Add service methods for `usage <name>` and bare `usage`, including managed/live target selection and duplicate suppression.
- [ ] 2.3 Persist refreshed credentials only for the queried managed snapshot and matching live auth file.
- [ ] 2.4 Add service tests for named queries, unmanaged live inclusion, duplicate suppression, refresh persistence, and per-account failure continuation.

## 3. CLI Rendering and Verification

- [ ] 3.1 Add the `usage` CLI command with an optional account name argument.
- [ ] 3.2 Render human-friendly 5-hour and weekly quota blocks with remaining percentages, reset times, credits information, and refresh notices.
- [ ] 3.3 Add CLI regression tests for successful output, named-account failures, and mixed-success batch results.
- [ ] 3.4 Update the README command examples and run focused plus full `uv run pytest` verification before marking the change complete.
