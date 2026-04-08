## 1. Transport Hardening

- [ ] 1.1 Add typed usage-network errors plus a usage-endpoint preflight probe in `src/codex_auth/errors.py` and `src/codex_auth/usage_api.py`.
- [ ] 1.2 Add explicit timeout handling for usage requests and map transport failures into stable operator-facing error types.
- [ ] 1.3 Add `tests/test_usage_api.py` coverage for reachable HTTP responses, unreachable preflight failures, and usage request timeouts.

## 2. Command Semantics

- [ ] 2.1 Run usage-endpoint preflight before named and batch usage queries in `src/codex_auth/service.py`.
- [ ] 2.2 Abort bare batch usage queries when any in-flight usage request times out, while keeping non-timeout per-account failures isolated.
- [ ] 2.3 Add `tests/test_service.py` coverage for preflight ordering, timeout-driven batch aborts, and continued handling of non-timeout account failures.
- [ ] 2.4 Add `tests/test_cli_read_commands.py` coverage for concise CLI surfacing of preflight and timeout failures.

## 3. Verification

- [ ] 3.1 Run `uv run pytest tests/test_usage_api.py tests/test_service.py tests/test_cli_read_commands.py -q`.
- [ ] 3.2 Run `uv run pytest -q`.
- [ ] 3.3 Mark this OpenSpec task list complete after implementation and verification.
