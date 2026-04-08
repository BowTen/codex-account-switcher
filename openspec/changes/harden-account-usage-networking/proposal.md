## Why

`codex-auth usage` 现在默认会直接进入批量查询，但当代理、DNS、出口网络或目标站点状态异常时，命令容易长时间等待后才失败，操作者也无法区分是账号问题还是链路问题。这个 change 需要先把 usage 查询的网络可达性和超时语义定义清楚，再继续扩展更复杂的交互体验。

## What Changes

- Add a usage-endpoint preflight check before named and batch usage queries start.
- Add explicit timeout handling for usage requests instead of relying on indefinite default blocking behavior.
- Fail the command immediately when the usage endpoint preflight check fails.
- Abort a bare batch `codex-auth usage` query when any in-flight account request times out.
- Preserve the current per-account continuation behavior for non-timeout refresh and usage failures.
- Add regression coverage for preflight, timeout mapping, and batch timeout abort semantics.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `account-usage`: define usage-endpoint reachability checks and timeout-driven command failure semantics for named and batch usage queries.

## Impact

- Affected code:
  - `src/codex_auth/errors.py`
  - `src/codex_auth/usage_api.py`
  - `src/codex_auth/service.py`
  - `src/codex_auth/cli.py`
  - `tests/test_usage_api.py`
  - `tests/test_service.py`
  - `tests/test_cli_read_commands.py`
- No credential storage format changes.
- No new API endpoints; the change only formalizes how the existing usage endpoint is probed and timed out.
- No changes to account switching, snapshot persistence, or transfer behavior outside usage-query execution flow.
