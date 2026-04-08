# Account Usage Reliability and Live View Design

## Goal

Improve `codex-auth usage` in two related but separable ways:

1. Make usage queries fail faster and more clearly when the network path to the usage endpoint is unavailable or times out.
2. Upgrade interactive terminal usage queries from delayed batch printing to a live view that shows query progress, active accounts, and incrementally rendered results.

The work is intentionally split into two OpenSpec changes so networking semantics and terminal UX can evolve independently:

- `harden-account-usage-networking`
- `add-account-usage-live-view`

## Scope

In scope:

- Preflight reachability checks against the ChatGPT usage endpoint before querying accounts
- Explicit timeout handling for usage requests
- Command-level failure semantics for reachability failures and request timeouts
- Interactive live rendering for bare `codex-auth usage`
- A bottom status area that shows running and queued accounts
- Incremental rendering of completed account results
- Dynamic result ordering by remaining quota
- Safe fallback to non-live plain-text output when stdout is not a TTY

Out of scope:

- Changes to `save`, `use`, `list`, `inspect`, `current`, `doctor`, `import`, or `export`
- New API endpoints beyond the existing usage endpoint
- Refresh endpoint reachability checks
- New user-facing flags for tuning concurrency, timeout, or sort order
- Persistent caching of usage responses
- Replacing the existing single-account query behavior with a fully interactive screen

## User Experience

### Networking and failure semantics

- Every `usage` command performs a lightweight preflight check against `https://chatgpt.com/backend-api/wham/usage` before any account query starts.
- If the usage endpoint is unreachable during preflight, the command fails immediately with a clear user-facing network error.
- Usage fetches run with an explicit timeout.
- For `codex-auth usage <name>`, a request timeout fails the command for that account.
- For bare `codex-auth usage`, if any account query times out, the whole batch aborts and the command exits non-zero.
- Non-timeout per-account failures keep their current isolated behavior:
  - refresh failure affects only that account
  - usage HTTP or payload failure affects only that account
  - other accounts continue unless a timeout occurs

### Interactive live view

- Bare `codex-auth usage` becomes a live terminal view when stdout is a TTY.
- The screen is divided into two regions:
  - result area on top for completed accounts
  - status area at the bottom for global phase plus running and queued accounts
- Query phases are visible:
  - `prechecking network`
  - `querying`
  - `completed`
  - `aborted (timeout)`
- Accounts stay in the status area until they complete.
- As each account finishes, it disappears from the status area and is inserted into the result area immediately.
- Failed accounts are rendered immediately as error results instead of waiting for the batch to finish.
- The status area remains anchored at the bottom while results above it grow.

### Ordering

- Completed successful accounts are sorted by quota pressure:
  - ascending `5h` remaining percentage
  - then ascending weekly remaining percentage
  - then stable account-name ordering
- This places lower remaining quota higher on the screen and higher remaining quota lower on the screen.
- Accounts that have not finished do not occupy placeholders in the result area.
- Error results appear ahead of successful quota-sorted results so failures stay visible.
- Non-TTY output keeps a stable plain-text format and applies the same final ordering without terminal redraw behavior.

## Architecture

### Change A: networking hardening

- Extend the usage API layer with:
  - a preflight reachability probe for the usage endpoint
  - explicit timeout-aware request execution
  - concise exception mapping for unreachable network vs timeout
- Keep the probe targeted only at the usage endpoint; do not probe the refresh endpoint.
- Keep timeout semantics centralized so named and batch usage flows use the same timeout behavior.

### Change B: live view rendering

- Add a CLI-side live rendering path that activates only when `sys.stdout.isatty()` is true and the operator runs bare `codex-auth usage`.
- Keep the existing non-interactive rendering path for redirected output, tests that do not need the live view, and any environment where redraw behavior would be inappropriate.
- Separate concerns into:
  - query orchestration state events
  - result rendering helpers
  - terminal repaint logic
- The service layer should expose enough progress information for the CLI to know:
  - which accounts are queued
  - which accounts are currently running
  - which account just completed with success or error

### Data flow

1. CLI detects whether it should use live view or plain-text mode.
2. Service performs usage endpoint preflight.
3. If preflight fails, the command exits before any per-account query begins.
4. Service enumerates targets in deterministic order.
5. Batch execution starts with bounded concurrency.
6. CLI receives progress updates and redraws:
   - queued accounts
   - running accounts
   - newly completed results
7. Successful results are re-sorted after each completion.
8. If any request times out, batch execution stops, the live view switches to `aborted (timeout)`, and the command exits non-zero.

## Error Handling

- Preflight failure is a command-level error, not a per-account error.
- Request timeout is a command-level error for batch usage and an account-level terminal error for named usage.
- Existing per-account refresh and usage fetch failures stay localized unless the failure is a timeout.
- Live view redraw failures must fall back to plain-text output rather than crashing the command.
- Terminal output must avoid exposing tokens or raw auth payloads in any error path.

## Testing

- Add usage API tests for:
  - reachability preflight success
  - reachability preflight failure
  - explicit timeout mapping
- Add service tests for:
  - batch abort when one account times out
  - non-timeout per-account errors still continue
  - deterministic target ordering remains intact
- Add CLI tests for:
  - non-TTY output preserving plain-text behavior
  - live view status transitions
  - live view status area reflecting running and queued accounts
  - incremental insertion of completed results
  - dynamic result ordering as accounts complete
  - timeout abort state rendering

## Risks and Tradeoffs

- A preflight check adds one extra network round trip, but it provides a much clearer failure mode when the usage endpoint is unreachable.
- Batch-wide timeout aborts are stricter than current per-account isolation, but this matches the requirement that hanging requests should not leave the operator waiting indefinitely.
- Live terminal redraw logic is more complex than plain printing, so non-TTY fallback remains important for stability.
- Sorting completed results after every update improves usability, but it means rows can move as new accounts finish; keeping unfinished accounts in the bottom status area avoids a noisier placeholder-based layout.
