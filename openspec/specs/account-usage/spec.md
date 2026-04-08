## Purpose
Describe how the CLI queries and renders Codex account usage limits for managed snapshots and the current live account.

## Requirements

### Requirement: Query usage for managed and current live accounts

The tool SHALL provide a `usage` command that queries saved managed accounts by default and also includes the current live `~/.codex/auth.json` account when it does not match a saved managed snapshot.

#### Scenario: Query all managed accounts by default
- **WHEN** the operator runs `codex-auth usage` and the managed store contains saved accounts
- **THEN** the tool queries usage for every saved managed account without requiring additional flags

#### Scenario: Include the current unmanaged live account
- **WHEN** the operator runs `codex-auth usage` and the current live `~/.codex/auth.json` exists but does not match any saved managed snapshot
- **THEN** the tool includes that live account in the usage results as an unmanaged account

#### Scenario: Query one named managed account
- **WHEN** the operator runs `codex-auth usage <name>` for an existing saved account
- **THEN** the tool queries only that managed account and does not include unrelated accounts in the output

### Requirement: Refresh expired ChatGPT OAuth credentials during usage queries

The tool SHALL refresh expired or near-expiry ChatGPT OAuth access tokens before querying usage and SHALL persist refreshed credentials only for the queried account and matching live auth file.

#### Scenario: Refresh a managed account before querying usage
- **WHEN** a managed account selected for usage inspection has an expired or near-expiry access token and refresh succeeds
- **THEN** the tool persists the refreshed credentials back into that managed snapshot before reporting usage

#### Scenario: Sync refreshed credentials to the live auth file
- **WHEN** the queried account is also the current live `~/.codex/auth.json` account and refresh succeeds
- **THEN** the tool writes the refreshed credentials back into the live auth file

#### Scenario: Continue after one account refresh fails
- **WHEN** one account in a batch usage query fails to refresh
- **THEN** the tool reports that account's failure and continues querying the remaining accounts

### Requirement: Render human-friendly quota information

The tool SHALL render usage results in a human-friendly terminal format that shows 5-hour and weekly quota state as remaining percentage, progress bars, and reset times.

#### Scenario: Show both rate limit windows
- **WHEN** the usage data includes both primary and secondary windows
- **THEN** the tool renders them as `5h limit` and `Weekly limit` with remaining percentages and localized reset times

#### Scenario: Prefer Unicode quota bars when available
- **WHEN** the operator runs `codex-auth usage` in a terminal environment that supports Unicode output
- **THEN** the tool renders quota progress bars with Unicode block characters instead of ASCII-only `#` and `-` bars

#### Scenario: Fall back safely when Unicode output is unsuitable
- **WHEN** the terminal output encoding is unsuitable for Unicode quota bars
- **THEN** the tool falls back to an ASCII-safe progress bar style without failing the command

#### Scenario: Show credits information when available
- **WHEN** the usage data includes credits details
- **THEN** the tool renders the available credits status and balance without exposing any tokens

#### Scenario: Mark an account that refreshed during the query
- **WHEN** the tool refreshes an account's credentials before fetching usage
- **THEN** the rendered output includes a concise indication that the token was refreshed

### Requirement: Degrade gracefully when usage cannot be fetched

The tool SHALL handle usage query failures on a per-account basis and SHALL avoid aborting an entire batch when one account fails.

#### Scenario: Report a named account lookup failure
- **WHEN** the operator runs `codex-auth usage <name>` for a missing managed account
- **THEN** the tool fails the command with a user-facing unknown-account error

#### Scenario: Report a per-account usage fetch failure in a batch
- **WHEN** one account in a batch usage query receives a non-success usage API response or invalid payload
- **THEN** the tool renders a concise error for that account and continues rendering successful account results

#### Scenario: Report missing rate limit data
- **WHEN** the usage API response does not include either rate limit window for an otherwise valid account
- **THEN** the tool reports that no rate limit data is available for that account instead of silently omitting it

### Requirement: Batch usage queries use bounded concurrency without reordering output

The tool SHALL execute bare `codex-auth usage` account queries with bounded concurrency to reduce total runtime while preserving deterministic result ordering.

#### Scenario: Query all accounts with bounded concurrency
- **WHEN** the operator runs bare `codex-auth usage` and multiple accounts need to be queried
- **THEN** the tool executes per-account usage queries concurrently with a fixed maximum concurrency of `4`

#### Scenario: Preserve output order during concurrent batch querying
- **WHEN** the operator runs bare `codex-auth usage` and account queries complete in different wall-clock orders
- **THEN** the tool renders results in the original deterministic account order instead of completion order

#### Scenario: Keep named account queries serial
- **WHEN** the operator runs `codex-auth usage <name>`
- **THEN** the tool queries only that account without invoking the batch concurrency path
