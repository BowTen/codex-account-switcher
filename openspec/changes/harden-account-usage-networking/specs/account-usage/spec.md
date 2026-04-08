## ADDED Requirements

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

## MODIFIED Requirements

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
