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

The tool SHALL handle non-timeout usage query failures on a per-account basis and SHALL avoid aborting an entire batch when one account fails for a reason other than endpoint reachability or request timeout.

#### Scenario: Report a named account lookup failure
- **WHEN** the operator runs `codex-auth usage <name>` for a missing managed account
- **THEN** the tool fails the command with a user-facing unknown-account error

#### Scenario: Report a per-account non-timeout usage fetch failure in a batch
- **WHEN** one account in a batch usage query receives a non-success usage API response, invalid payload, or refresh failure without timing out
- **THEN** the tool renders a concise error for that account and continues rendering successful account results

#### Scenario: Report missing rate limit data
- **WHEN** the usage API response does not include either rate limit window for an otherwise valid account
- **THEN** the tool reports that no rate limit data is available for that account instead of silently omitting it

### Requirement: Batch usage queries use bounded concurrency with quota-priority presentation

The tool SHALL execute bare `codex-auth usage` account queries with bounded concurrency to reduce total runtime while presenting completed results by quota priority instead of raw completion order.

#### Scenario: Query all accounts with bounded concurrency
- **WHEN** the operator runs bare `codex-auth usage` and multiple accounts need to be queried
- **THEN** the tool executes per-account usage queries concurrently with a fixed maximum concurrency of `4`

#### Scenario: Present completed results by remaining quota priority
- **WHEN** multiple account results are available during or after a batch usage query
- **THEN** the tool presents successful results ordered by ascending `5h` remaining percentage, then ascending weekly remaining percentage, with lower remaining quota higher on the screen

#### Scenario: Keep errors visible ahead of successful sorted results
- **WHEN** some completed accounts have usage errors and others complete successfully
- **THEN** the tool presents the errored accounts ahead of the successful quota-sorted results so failures remain visible

#### Scenario: Keep named account queries serial
- **WHEN** the operator runs `codex-auth usage <name>`
- **THEN** the tool queries only that account without invoking the batch concurrency path

### Requirement: Interactive batch usage queries show live query status

The tool SHALL render bare `codex-auth usage` as a live terminal view when stdout is an interactive TTY, with completed results above and query status below.

#### Scenario: Show the current phase plus running and queued accounts
- **WHEN** the operator runs bare `codex-auth usage` in an interactive TTY
- **THEN** the tool renders a bottom status area that shows the current query phase plus the currently running and queued account names

#### Scenario: Insert completed accounts into the result area as they finish
- **WHEN** an account finishes during an interactive batch usage query
- **THEN** the tool removes that account from the bottom status area and immediately renders its result in the top result area

#### Scenario: Fall back to plain-text output outside interactive terminals
- **WHEN** the operator runs bare `codex-auth usage` with stdout redirected or otherwise not attached to a TTY
- **THEN** the tool skips live terminal redraw behavior and renders stable plain-text output instead

### Requirement: Usage queries preflight the usage endpoint before account fetches

The tool SHALL probe the ChatGPT usage endpoint before starting any named or batch usage query and SHALL treat any HTTP response from that endpoint as proof of reachability.

#### Scenario: Continue after a reachable endpoint returns an HTTP response
- **WHEN** the preflight request reaches `https://chatgpt.com/backend-api/wham/usage` and receives any HTTP response before account queries begin
- **THEN** the tool treats the endpoint as reachable and continues into the named or batch usage query flow

#### Scenario: Fail fast when the usage endpoint is unreachable
- **WHEN** the preflight request cannot reach `https://chatgpt.com/backend-api/wham/usage` before account queries begin
- **THEN** the tool fails the command immediately with a user-facing network error and does not start any per-account usage query

### Requirement: Usage request timeouts terminate usage commands

The tool SHALL apply an explicit timeout to usage requests and SHALL treat timeout failures as command-level failures rather than ordinary per-account usage errors.

#### Scenario: Fail a named usage query on timeout
- **WHEN** the operator runs `codex-auth usage <name>` and that account's usage request times out
- **THEN** the tool fails the command with a user-facing timeout error

#### Scenario: Abort a batch usage query when one account times out
- **WHEN** the operator runs bare `codex-auth usage` and any in-flight account usage request times out
- **THEN** the tool aborts the batch, exits non-zero, and does not continue waiting for the remaining accounts to finish
