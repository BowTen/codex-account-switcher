## Context

`codex-auth usage` has already shipped, but the first version optimized for correctness rather than operator experience. Two issues are now clear in real usage:

- The current ASCII-only progress bars look noticeably worse than the intended terminal presentation.
- Bare `codex-auth usage` executes account queries serially, so total runtime grows linearly with the number of accounts.

The implementation already has a good separation between CLI rendering in `src/codex_auth/cli.py` and query execution in `src/codex_auth/service.py`, so this change can stay small if rendering improvements remain in the CLI layer and bounded concurrency remains in the service layer.

## Goals / Non-Goals

**Goals:**
- Improve the default quota bar appearance with Unicode-first rendering.
- Keep batch usage output in a stable, deterministic order.
- Reduce wall-clock time for bare `codex-auth usage` by querying multiple accounts concurrently with a bounded default concurrency of `4`.
- Preserve existing error isolation, refresh persistence, and named-account semantics.

**Non-Goals:**
- No new CLI flags or configuration surface.
- No usage-result caching.
- No changes to credential storage, refresh protocol, or API payload shape.
- No concurrency changes for `codex-auth usage <name>`.

## Decisions

### 1. Keep rendering logic in the CLI layer

The CLI already owns the text formatting contract, so Unicode bar rendering should stay in `src/codex_auth/cli.py`. This keeps presentation changes isolated from service behavior and makes regression testing straightforward.

Alternative considered:
- Move rendering into the service result model.
Why rejected:
- It would mix transport/data concerns with terminal presentation and make future non-CLI reuse harder.

### 2. Use Unicode bars by default, with a silent ASCII fallback

The default bar style will switch from `#`/`-` to filled and empty block characters. If stdout encoding cannot safely represent Unicode, the renderer will silently fall back to the existing ASCII-safe style.

Alternative considered:
- Always emit Unicode.
Why rejected:
- It risks unreadable output in non-UTF-8 or restricted terminal environments.

### 3. Add bounded concurrency only for batch usage queries

`CodexAuthService.list_usage_accounts()` will execute per-account fetches concurrently with a fixed maximum concurrency of `4`, but it will still return results in the original target order. `get_usage_account()` remains serial.

Alternative considered:
- Make both named and batch queries share the same concurrent path.
Why rejected:
- Named queries do not benefit from concurrency, and keeping them serial avoids unnecessary complexity.

### 4. Keep concurrency in the service layer, not the CLI

The service layer already owns target enumeration, per-account error shaping, and refresh persistence semantics. Adding bounded concurrency there keeps the CLI simple and prevents output code from having to reason about futures, worker pools, or synchronization.

Alternative considered:
- Have the CLI dispatch multiple service calls concurrently.
Why rejected:
- It would duplicate execution policy in the presentation layer and make ordering/error handling more fragile.

## Risks / Trade-offs

- [Higher request burst against backend] → Use a fixed low default concurrency of `4` rather than unbounded parallelism.
- [Unicode bars may render poorly in some environments] → Detect unsuitable output encoding and fall back to ASCII silently.
- [Concurrency can reorder results or complicate persistence] → Build targets in deterministic order, collect worker results by original index, and keep existing per-account persistence logic unchanged.
