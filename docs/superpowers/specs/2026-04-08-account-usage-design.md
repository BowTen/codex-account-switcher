# Account Usage Design

**Date:** 2026-04-08

**Goal:** Add a human-friendly usage command that can query Codex rate limit information for all managed accounts, a named managed account, and the current unmanaged live account.

## Scope

This design extends the existing account snapshot CLI with rate limit inspection for ChatGPT-backed accounts.

Included:
- Add `codex-auth usage [name]`.
- Query usage for all saved managed accounts when `usage` is run without a name.
- Include the current live `~/.codex/auth.json` account in the default `usage` output when it does not match a managed account.
- Query usage for one named managed account when `usage <name>` is used.
- Fetch usage from the ChatGPT backend usage API instead of parsing `codex login status`.
- Automatically refresh expired or near-expiry ChatGPT access tokens before usage requests.
- Persist refreshed tokens back into the corresponding managed snapshot, and also update `~/.codex/auth.json` when the refreshed account is the current live account.
- Render human-friendly output with 5-hour and weekly usage bars, remaining percentages, and reset times.

Excluded from this design:
- JSON or machine-readable output formats.
- Sorting and filtering options beyond the default account ordering.
- Querying usage for API key based accounts.
- Converting the current unmanaged live account into a managed snapshot automatically.
- Any changes to `save`, `use`, `current`, `inspect`, `export`, `import`, or `doctor` behavior.

## User Experience

The new command surface is:

- `codex-auth usage`
- `codex-auth usage <name>`

### Default Usage Query

`codex-auth usage` should:

1. Load all managed accounts from the local store.
2. Detect whether the current live `~/.codex/auth.json` matches an existing managed account.
3. If the live account is unmanaged, add it to the query set as a separate unmanaged result.
4. Query usage for each selected account independently.
5. Continue through the full set even if one account fails.
6. Print one human-friendly block per account.

### Named Usage Query

`codex-auth usage <name>` should:

1. Validate that `<name>` is an existing managed account.
2. Query only that managed account.
3. Print one human-friendly account block.

### Rendering

Each account block should show:

- Account display name.
- Managed state: `managed` or `unmanaged`.
- Plan type when available.
- A redacted account identifier summary.
- `5h limit` as a textual progress bar and remaining percentage.
- `Weekly limit` as a textual progress bar and remaining percentage.
- Reset time in the local timezone in a human-readable form such as `resets 01:04 on 7 Apr`.
- Credits information when present.
- A short note when the account token was refreshed during the query.

If usage cannot be queried for an account, the output should show a concise per-account error message instead of aborting the entire command.

Default output order should be:

- The current unmanaged live account first, when it is included.
- Managed accounts after that, sorted by account name.

### Interaction Principles

- The command should remain non-interactive.
- Output should be optimized for operators reading the terminal, not for scripts.
- The default multi-account query should avoid duplicate output for the same live account and matching managed account.
- Unsupported account types should be reported explicitly as unavailable for usage inspection.

## Architecture

The feature should preserve the current `argparse` CLI and existing service/store layering.

Recommended module layout:

- `src/codex_auth/cli.py`
  Add `usage` command parsing and output rendering.
- `src/codex_auth/service.py`
  Add orchestration methods for named and batch usage queries.
- `src/codex_auth/store.py`
  Add helpers to read and persist refreshed token fields for managed snapshots and the live auth file.
- `src/codex_auth/models.py`
  Add data models for usage windows, usage results, query targets, and refresh outcomes.
- `src/codex_auth/usage_api.py`
  Handle usage API requests and payload parsing.
- `src/codex_auth/token_refresh.py`
  Handle token expiry checks, refresh requests, and refresh result normalization.
- `src/codex_auth/validators.py`
  Reuse snapshot parsing and add minimal helpers for token access if needed.

The key boundary is:

- `service.py` owns account selection, deduplication, refresh orchestration, and result aggregation.
- `usage_api.py` owns HTTP requests and response parsing for the ChatGPT usage endpoint.
- `token_refresh.py` owns token expiry detection and OAuth refresh calls.
- `cli.py` owns human-friendly terminal rendering only.

This keeps the network-facing pieces testable without coupling them to CLI formatting.

## Usage Data Source

The usage command should use the ChatGPT backend usage endpoint:

- `GET https://chatgpt.com/backend-api/wham/usage`

The request should include:

- `Authorization: Bearer <access_token>`
- `chatgpt-account-id: <account_id>`
- `User-Agent: codex-cli/1.0.0`

This design intentionally does not depend on `codex login status` because:

- Current local testing showed that `codex login status` may return only basic login state without usage data.
- The ChatGPT usage endpoint returns structured usage information including primary and secondary rate limit windows.
- Structured JSON is materially more stable than CLI text scraping.

## Token Refresh Design

Usage queries should refresh ChatGPT OAuth tokens only when needed.

### Refresh Trigger

Before sending a usage request, the command should inspect the access token expiry. If the token is expired or within a small expiry buffer, it should attempt refresh.

### Refresh Request

Refresh should use:

- The account's stored `refresh_token`
- A built-in OAuth `client_id` compatible with the current Codex/ChatGPT flow
- The OAuth token endpoint at `https://auth.openai.com/oauth/token`

The command should not require operator input for refresh.

### Refresh Persistence

When refresh succeeds:

- Update the queried account's stored `access_token`
- Update `id_token` when the refresh response includes a new one
- Update `refresh_token` when the refresh response includes a new one
- Update `account_id` when a refreshed ID token yields a more current value
- Keep `last_refresh` metadata in sync with the refreshed live snapshot state

If the refreshed account corresponds to the current live account, the command should also write the refreshed token set back to `~/.codex/auth.json`.

If refresh fails for one account, the command should report that account's failure and continue querying the other accounts.

## Query Target Selection

The service layer should treat usage queries as operations over explicit query targets rather than over registry entries alone.

Target types:

- Managed account target backed by a saved snapshot and registry entry
- Unmanaged live target backed only by the current `~/.codex/auth.json`

Selection rules:

- `usage <name>` selects exactly one managed target.
- Bare `usage` selects all managed targets.
- Bare `usage` adds one unmanaged live target only when the current live auth exists and does not match any saved managed snapshot identity.
- If the live auth matches a saved managed account, it should not be emitted twice.

## Output Rules

The CLI should render usage based on remaining percentage, not used percentage, because the operator cares about how much quota is left.

For each limit window:

- Remaining percent = `max(0, 100 - used_percent)`.
- The label should use `5h limit` for the primary window and `Weekly limit` for the secondary window.
- The progress bar should be fixed-width ASCII or block-character based and visually emphasize remaining quota.
- Reset timestamps should be converted to the local timezone before rendering.

If a window is missing:

- Show a concise "No rate limit data" style message for that account or section.

If credits data is present:

- Show whether credits exist and, when available, the current balance.

## Failure Behavior

The command should degrade per account rather than fail as a batch.

Failure cases and expected behavior:

- No managed accounts and no live auth file: fail with a clear user-facing error.
- Missing live auth file for unmanaged query: omit unmanaged result.
- Unknown managed account name: fail the command with a user-facing error.
- Missing required token fields: show an error block for that account.
- Refresh failure: show a per-account error block and continue.
- Usage API non-2xx response: show a per-account error block and continue.
- Usage API payload missing both limit windows: show that no rate limit data is available.
- Unsupported account auth mode: show that usage is unavailable for that account type.

The command exit behavior should remain simple:

- Return success when at least one account query completes and renders a result block.
- Return failure when a named query fails before any account can be queried, or when every selected account fails.

## Security Considerations

- The command must never print raw `access_token`, `refresh_token`, or `id_token`.
- Error messages should avoid echoing sensitive response bodies that may include confidential fields.
- Refreshed tokens should be written through the same atomic file replacement pattern already used for snapshots and registry files.
- The unmanaged live account should be queried in memory and only written back when refresh succeeds and the live auth is the refreshed target.

## Testing Strategy

The feature should be implemented with test-first coverage at the token, API, service, and CLI layers.

### Token Refresh Tests

Add tests to cover:

- Detecting expired and near-expiry access tokens.
- Refresh success with updated token fields.
- Refresh success when the response omits a replacement refresh token.
- Refresh failure propagation without partial writes.

### Usage API Tests

Add tests to cover:

- Successful parsing of primary and secondary rate limit windows.
- Missing credits fields.
- Non-2xx API responses.
- Invalid JSON responses.

### Service Tests

Add tests to cover:

- Querying one named managed account.
- Querying all managed accounts.
- Including one unmanaged live account in bare `usage`.
- Suppressing duplicate output when live auth matches a managed account.
- Persisting refreshed tokens for managed accounts.
- Syncing refreshed tokens to live auth when the refreshed account is current.
- Continuing after one account query fails in a multi-account run.

### CLI Tests

Add tests to cover:

- `usage` command parsing.
- Human-friendly output for one account with both usage windows.
- Human-friendly output when one account has an error.
- Named account errors.

## Open Questions Resolved

- Data source: use the ChatGPT usage endpoint, not `codex login status`.
- Default scope: bare `usage` queries all managed accounts plus the current unmanaged live account.
- Refresh behavior: automatic refresh is allowed and should persist refreshed tokens.
- Output style: human-friendly terminal blocks are the default and only initial format.
