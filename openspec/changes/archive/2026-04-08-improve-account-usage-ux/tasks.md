## 1. Batch Query Concurrency

- [x] 1.1 Add bounded concurrent execution to bare `codex-auth usage` batch queries in the service layer.
- [x] 1.2 Preserve deterministic result ordering while collecting concurrent batch results.
- [x] 1.3 Keep named-account usage queries on the existing serial path.
- [x] 1.4 Add service tests for bounded concurrency, stable output ordering, and per-account failure continuation under concurrent execution.

## 2. Rendering Improvements

- [x] 2.1 Replace the current ASCII-first quota bars with a Unicode-first progress bar renderer in the CLI.
- [x] 2.2 Add a silent ASCII fallback when Unicode bar rendering is unsuitable for the current output encoding.
- [x] 2.3 Keep the current usage text structure while improving rendered progress bar readability.
- [x] 2.4 Add CLI tests for representative Unicode rendering and ASCII fallback behavior.

## 3. Verification and Documentation

- [x] 3.1 Update the README usage examples only if the operator-facing output guidance needs clarification.
- [x] 3.2 Run focused usage-related tests for service and CLI behavior.
- [x] 3.3 Run the full `uv run pytest -q` suite and verify the change remains green.
- [x] 3.4 Mark the OpenSpec task list complete after implementation and verification.
