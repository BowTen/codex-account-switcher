## ADDED Requirements

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

## RENAMED Requirements

### Requirement: Batch usage queries use bounded concurrency without reordering output
- FROM: `Batch usage queries use bounded concurrency without reordering output`
- TO: `Batch usage queries use bounded concurrency with quota-priority presentation`

## MODIFIED Requirements

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
