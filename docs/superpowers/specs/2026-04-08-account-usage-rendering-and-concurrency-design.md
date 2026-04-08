# Account Usage Rendering and Concurrency Design

## Goal

Improve the `codex-auth usage` experience in two targeted ways:

1. Replace the current plain ASCII progress bars with a more readable Unicode quota bar style.
2. Reduce total runtime for bare `codex-auth usage` by querying multiple accounts concurrently while keeping output order stable.

## Scope

In scope:

- Human-friendly Unicode progress bar rendering for usage output
- ASCII fallback when Unicode rendering is not appropriate
- Default concurrent querying for bare `codex-auth usage`
- Stable output ordering despite concurrent execution
- Regression coverage for rendering and batch execution behavior

Out of scope:

- New CLI flags
- Result caching
- API contract changes
- Changes to named-account `codex-auth usage <name>` execution model

## User Experience

### Rendering

- Replace the current `#` / `-` progress bars with block-style bars such as `████░░░░░░`.
- Keep labels unchanged: `5h limit` and `Weekly limit`.
- Continue showing remaining percentage, reset time, credits information, and refresh notices.
- If the terminal environment appears unsuitable for Unicode output, fall back to the existing ASCII-safe bar style rather than failing.

### Concurrency

- `codex-auth usage <name>` remains single-account and serial.
- Bare `codex-auth usage` runs account queries concurrently with a fixed maximum concurrency of `4`.
- Results are rendered in the same deterministic order as today’s target enumeration, so concurrency does not reorder output.
- Per-account failures remain isolated: one failed account still does not abort the whole batch.

## Architecture

### CLI Rendering

- Keep rendering logic in `src/codex_auth/cli.py`.
- Replace the current progress bar helper with a style-aware helper:
  - Unicode bar by default
  - ASCII fallback when necessary
- Preserve the current text structure so downstream parsing expectations are not broadened unnecessarily.

### Service Concurrency

- Keep single-account querying logic unchanged.
- Add a batch-only concurrent execution path in `src/codex_auth/service.py`.
- Build the full ordered target list first.
- Execute fetches under a bounded worker pool with maximum concurrency `4`.
- Reassemble results in the original target order before returning to the CLI.

This keeps concurrency inside the service layer, where query behavior already lives, and avoids mixing execution control into CLI code.

## Error Handling

- If a worker raises for one account, convert it into that account’s existing error result and continue.
- Concurrency must not weaken the current refresh-persistence guarantees:
  - refreshed credentials are still persisted for the queried managed snapshot
  - matching live auth is still updated
- Unicode fallback should be silent; rendering should degrade, not warn.

## Testing

- Add CLI rendering tests that assert at least one representative Unicode bar output.
- Add a fallback rendering test for ASCII mode if fallback logic is introduced explicitly.
- Add service tests proving:
  - bare `usage` preserves output ordering under concurrent execution
  - batch execution still continues after one account failure
  - concurrency only applies to multi-account listing, not named queries

## Risks and Tradeoffs

- Higher concurrency can increase request bursts against the backend, so the default is capped at `4` instead of scaling aggressively.
- Unicode bars look better, but some terminal environments may render them poorly; fallback handling prevents this from becoming a hard failure.
- Concurrency adds implementation complexity, so the change is intentionally constrained to batch queries only.
