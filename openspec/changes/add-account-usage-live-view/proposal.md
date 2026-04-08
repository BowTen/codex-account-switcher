## Why

`codex-auth usage` 已经能查询额度，但当前交互仍然像一个黑盒：查询期间看不到进度，结果要等全部账号完成后才一次性出现，也无法根据额度压力快速定位最紧张的账号。这个 change 把 bare `usage` 升级成实时终端视图，让操作者在查询过程中就能看到状态和结果。

## What Changes

- Add a live TTY rendering mode for bare `codex-auth usage`.
- Show a bottom status area with the current phase plus running and queued account names.
- Render completed account results incrementally instead of waiting for the full batch to finish.
- Sort completed successful results by remaining 5-hour quota, then remaining weekly quota, with lower remaining quota higher on screen.
- Keep errors visible ahead of successful sorted results.
- Preserve a plain-text fallback path for non-TTY output such as redirection or piping.
- Add regression coverage for live progress rendering, dynamic ordering, and non-TTY fallback behavior.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `account-usage`: extend bare usage queries with live terminal state display and quota-priority result ordering while keeping redirected output text-safe.

## Impact

- Affected code:
  - `src/codex_auth/models.py`
  - `src/codex_auth/service.py`
  - `src/codex_auth/cli.py`
  - `tests/test_service.py`
  - `tests/test_cli_read_commands.py`
  - `README.md`
- No credential storage format changes.
- No new external dependencies; the live view should rely on stdlib terminal output primitives.
- No changes to named-account switching, snapshot storage, transfer workflows, or usage API payload format.
