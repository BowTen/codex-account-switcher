## 1. Batch Query Concurrency

- [ ] 1.1 Add bounded concurrent execution to bare `codex-auth usage` batch queries in the service layer.
- [ ] 1.2 Preserve deterministic result ordering while collecting concurrent batch results.
- [ ] 1.3 Keep named-account usage queries on the existing serial path.
- [ ] 1.4 Add service tests for bounded concurrency, stable output ordering, and per-account failure continuation under concurrent execution.

## 2. Rendering Improvements

- [ ] 2.1 Replace the current ASCII-first quota bars with a Unicode-first progress bar renderer in the CLI.
- [ ] 2.2 Add a silent ASCII fallback when Unicode bar rendering is unsuitable for the current output encoding.
- [ ] 2.3 Keep the current usage text structure while improving rendered progress bar readability.
- [ ] 2.4 Add CLI tests for representative Unicode rendering and ASCII fallback behavior.

## 3. Verification and Documentation

- [ ] 3.1 Update the README usage examples only if the operator-facing output guidance needs clarification.
- [ ] 3.2 Run focused usage-related tests for service and CLI behavior.
- [ ] 3.3 Run the full `uv run pytest -q` suite and verify the change remains green.
- [ ] 3.4 Mark the OpenSpec task list complete after implementation and verification.
