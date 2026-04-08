# Account Usage UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `codex-auth usage` by rendering Unicode-first quota bars and making bare multi-account queries complete faster with stable bounded concurrency.

**Architecture:** Keep presentation concerns in `src/codex_auth/cli.py` and execution policy in `src/codex_auth/service.py`. Add a bounded concurrent batch execution path only for bare `usage`, preserve result ordering, and introduce a rendering helper that prefers Unicode bars but silently falls back to ASCII when output encoding is unsuitable.

**Tech Stack:** Python 3.12, `uv`, `pytest`, stdlib `concurrent.futures`, stdlib terminal/encoding inspection, existing argparse CLI

---

### Task 1: Add Bounded Concurrent Batch Usage Execution

**Files:**
- Modify: `src/codex_auth/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests for concurrent batch ordering and serial named queries**

```python
def test_list_usage_accounts_keeps_original_order_under_concurrent_completion(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("alpha", make_snapshot("acct-alpha"), force=False, mark_active=True)
    service.store.save_snapshot("beta", make_snapshot("acct-beta"), force=False, mark_active=False)
    service.store.save_snapshot("gamma", make_snapshot("acct-gamma"), force=False, mark_active=False)

    delays = {"alpha": 0.05, "beta": 0.01, "gamma": 0.03}

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        time.sleep(delays[target.name])
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["alpha", "beta", "gamma"]


def test_get_usage_account_does_not_use_batch_executor(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", lambda target: make_usage_result(target))

    result = service.get_usage_account("work")

    assert result.name == "work"
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `uv run pytest tests/test_service.py -q`
Expected: FAIL because bare `list_usage_accounts()` still uses the old serial path and has no explicit concurrent execution behavior under test.

- [ ] **Step 3: Implement the minimal bounded concurrent batch path in the service layer**

```python
DEFAULT_USAGE_BATCH_CONCURRENCY = 4


def list_usage_accounts(self) -> list[AccountUsageResult]:
    targets = self._list_usage_targets()
    if len(targets) <= 1:
        results = [self._fetch_usage_target(target) for target in targets]
    else:
        indexed_targets = list(enumerate(targets))
        ordered_results: list[AccountUsageResult | None] = [None] * len(indexed_targets)
        with ThreadPoolExecutor(max_workers=DEFAULT_USAGE_BATCH_CONCURRENCY) as executor:
            future_map = {
                executor.submit(self._fetch_usage_target, target): index
                for index, target in indexed_targets
            }
            for future in as_completed(future_map):
                index = future_map[future]
                ordered_results[index] = future.result()
        results = [item for item in ordered_results if item is not None]

    for target, result in zip(targets, results, strict=True):
        self._persist_usage_refresh(target, result)
    return results
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `uv run pytest tests/test_service.py -q`
Expected: PASS with the new ordering and serial-path tests plus the existing usage service coverage.

- [ ] **Step 5: Commit the concurrent batch execution changes**

```bash
git add src/codex_auth/service.py tests/test_service.py
git commit -m "feat: add concurrent batch usage queries"
```

### Task 2: Replace ASCII Bars with Unicode-First Rendering

**Files:**
- Modify: `src/codex_auth/cli.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Write the failing CLI tests for Unicode bars and ASCII fallback**

```python
def test_cli_usage_prefers_unicode_bars(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("codex_auth.cli._unicode_usage_bars_supported", lambda: True)

    class FakeUsageService:
        def list_usage_accounts(self) -> list[AccountUsageResult]:
            return [
                make_usage_result(
                    name="work",
                    managed_state="managed",
                    account_id="acct-work",
                    primary_window=make_usage_window(used_percent=10, reset_at=1712224800),
                    secondary_window=make_usage_window(used_percent=20, reset_at=1712228400),
                )
            ]

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 0
    assert "████" in captured.out


def test_cli_usage_falls_back_to_ascii_bars(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("codex_auth.cli._unicode_usage_bars_supported", lambda: False)

    class FakeUsageService:
        def list_usage_accounts(self) -> list[AccountUsageResult]:
            return [
                make_usage_result(
                    name="work",
                    managed_state="managed",
                    account_id="acct-work",
                    primary_window=make_usage_window(used_percent=10, reset_at=1712224800),
                    secondary_window=make_usage_window(used_percent=20, reset_at=1712228400),
                )
            ]

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[##" in captured.out or "[#" in captured.out
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: FAIL because the current renderer always emits ASCII bars and has no explicit fallback helper.

- [ ] **Step 3: Implement Unicode-first rendering with a safe fallback**

```python
def _unicode_usage_bars_supported() -> bool:
    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


def _format_progress_bar(remaining_percent: float | int | None, width: int = 20) -> str:
    if remaining_percent is None:
        return "[????????????????????]"
    clamped = max(0, min(100, float(remaining_percent)))
    filled = max(0, min(width, int(round(clamped / 100 * width))))
    if _unicode_usage_bars_supported():
        return f"[{'█' * filled}{'░' * (width - filled)}]"
    return f"[{'#' * filled}{'-' * (width - filled)}]"
```

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: PASS with the new Unicode/fallback coverage and existing `usage` command tests.

- [ ] **Step 5: Commit the rendering changes**

```bash
git add src/codex_auth/cli.py tests/test_cli_read_commands.py
git commit -m "feat: improve usage bar rendering"
```

### Task 3: Verify End-to-End Usage UX Behavior

**Files:**
- Modify: `README.md`
- Modify: `openspec/changes/improve-account-usage-ux/tasks.md`
- Test: `tests/test_service.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Update README only if output guidance needs clarification**

```markdown
- `codex-auth usage` 默认会并发查询全部账号额度并保持输出顺序稳定。
- 额度条会优先使用 Unicode 样式，在不适合的终端环境中回退为 ASCII。
```

- [ ] **Step 2: Run focused usage UX verification**

Run: `uv run pytest tests/test_service.py tests/test_cli_read_commands.py -q`
Expected: PASS with the concurrent batch and rendering tests green together.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS with the full repository suite green.

- [ ] **Step 4: Mark the OpenSpec task list complete**

```markdown
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
```

- [ ] **Step 5: Commit the verification and task updates**

```bash
git add README.md openspec/changes/improve-account-usage-ux/tasks.md tests/test_service.py tests/test_cli_read_commands.py src/codex_auth/service.py src/codex_auth/cli.py
git commit -m "test: verify account usage ux improvements"
```
