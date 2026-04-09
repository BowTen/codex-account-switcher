## 1. Progress Event Infrastructure

- [x] 1.1 Add usage batch progress-event models in `src/codex_auth/models.py` for phase, running, queued, completed, and aborted states.
- [x] 1.2 Add a streaming batch usage API in `src/codex_auth/service.py` that emits progress events while preserving bounded concurrency.
- [x] 1.3 Add `tests/test_service.py` coverage for progress-event emission and timeout-abort event behavior.

## 2. Interactive Live View

- [x] 2.1 Add live usage rendering helpers in `src/codex_auth/cli.py` for the bottom status area and top completed-results area.
- [x] 2.2 Sort completed successful results by ascending 5-hour remaining quota, then ascending weekly remaining quota, while keeping errored results visible first.
- [x] 2.3 Render completed account results incrementally as progress events arrive instead of waiting for the full batch to finish.
- [x] 2.4 Add `tests/test_cli_read_commands.py` coverage for live status rendering, incremental result insertion, and quota-priority ordering.

## 3. Fallback and Verification

- [x] 3.1 Keep redirected and non-TTY bare `usage` output on a stable plain-text path.
- [x] 3.2 Update `README.md` only if the live-view versus plain-text behavior needs operator-facing clarification.
- [x] 3.3 Run `uv run pytest tests/test_service.py tests/test_cli_read_commands.py -q`.
- [x] 3.4 Run `uv run pytest -q`.
- [x] 3.5 Mark this OpenSpec task list complete after implementation and verification.
