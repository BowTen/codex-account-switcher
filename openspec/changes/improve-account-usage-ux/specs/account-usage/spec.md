## MODIFIED Requirements

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

## ADDED Requirements

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
