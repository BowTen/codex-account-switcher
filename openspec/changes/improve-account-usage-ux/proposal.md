## Why

The new `codex-auth usage` command works functionally, but two parts of the operator experience are still weak: the quota bars use plain ASCII output that looks noticeably worse than the intended terminal style, and bare multi-account queries are executed serially, which makes the command feel slow as the number of accounts grows.

## What Changes

- Replace the current ASCII-only quota bar rendering with a Unicode-first rendering style, while preserving a safe ASCII fallback when Unicode output is not appropriate.
- Change bare `codex-auth usage` to query multiple accounts concurrently with a bounded default concurrency of `4`.
- Preserve stable output ordering so concurrency improves latency without making the output harder to read.
- Keep named-account `codex-auth usage <name>` behavior serial and unchanged apart from rendering improvements.
- Add regression coverage for Unicode rendering, CLI output shape, and concurrent batch execution behavior.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `account-usage`: improve human-friendly usage rendering and define bounded concurrent execution for batch usage queries.

## Impact

- Affected code:
  - `src/codex_auth/cli.py`
  - `src/codex_auth/service.py`
  - `tests/test_cli_read_commands.py`
  - `tests/test_service.py`
  - `README.md`
- No API endpoint changes.
- No credential storage format changes.
- No account switching, transfer, or snapshot semantics change outside usage-query execution and rendering.
