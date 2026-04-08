# Account Usage Live View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn bare `codex-auth usage` into a live TTY view that shows query progress, running accounts, and incrementally sorted results while preserving plain-text fallback for non-interactive output.

**Architecture:** Keep target enumeration, concurrency, and completion events in `src/codex_auth/service.py`, add explicit usage-batch progress models in `src/codex_auth/models.py`, and implement terminal redraw logic in `src/codex_auth/cli.py`. Non-TTY execution should remain on the existing plain-text path, while TTY batch execution switches to a progress-event-driven live renderer.

**Tech Stack:** Python 3.12, `uv`, `pytest`, stdlib terminal I/O, stdlib `concurrent.futures`, existing argparse CLI

---

### Task 1: Add Progress Event Models and Streaming Service Coverage

**Files:**
- Modify: `src/codex_auth/models.py`
- Modify: `src/codex_auth/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests for progress events and timeout abort events**

```python
def test_stream_usage_accounts_emits_running_and_completed_events(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("alpha", make_snapshot("acct-alpha"), force=False, mark_active=True)
    service.store.save_snapshot("beta", make_snapshot("acct-beta"), force=False, mark_active=False)

    monkeypatch.setattr("codex_auth.service.probe_usage_endpoint", lambda: None)
    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: make_usage_result(target),
    )

    events = list(service.stream_usage_accounts())

    assert events[0].phase == "prechecking network"
    assert any(event.kind == "account-started" and event.running_names for event in events)
    assert any(event.kind == "account-finished" and event.result is not None for event in events)
    assert events[-1].phase == "completed"


def test_stream_usage_accounts_emits_abort_event_on_timeout(tmp_path, monkeypatch) -> None:
    from codex_auth.errors import UsageTimeoutError

    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("alpha", make_snapshot("acct-alpha"), force=False, mark_active=True)
    service.store.save_snapshot("beta", make_snapshot("acct-beta"), force=False, mark_active=False)

    monkeypatch.setattr("codex_auth.service.probe_usage_endpoint", lambda: None)

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        if target.name == "alpha":
            raise UsageTimeoutError("usage request timed out")
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    events = list(service.stream_usage_accounts())

    assert events[-1].phase == "aborted (timeout)"
    assert events[-1].error == "usage request timed out"
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `uv run pytest tests/test_service.py -q`
Expected: FAIL because there is no streaming usage event API or timeout abort event model.

- [ ] **Step 3: Add progress-event dataclasses and a streaming batch query method**

```python
@dataclass(slots=True)
class UsageBatchEvent:
    kind: str
    phase: str
    queued_names: list[str]
    running_names: list[str]
    result: AccountUsageResult | None = None
    error: str | None = None


def stream_usage_accounts(self) -> Iterator[UsageBatchEvent]:
    targets = self._list_usage_targets()
    queued_names = [target.name for target in targets]
    running_names: list[str] = []

    yield UsageBatchEvent(kind="phase", phase="prechecking network", queued_names=queued_names, running_names=[])
    probe_usage_endpoint()
    yield UsageBatchEvent(kind="phase", phase="querying", queued_names=list(queued_names), running_names=[])

    with ThreadPoolExecutor(max_workers=USAGE_BATCH_MAX_WORKERS) as executor:
        futures = {}
        for target in targets[:USAGE_BATCH_MAX_WORKERS]:
            queued_names.remove(target.name)
            running_names.append(target.name)
            future = executor.submit(self._fetch_usage_target, target)
            futures[future] = target
            yield UsageBatchEvent(
                kind="account-started",
                phase="querying",
                queued_names=list(queued_names),
                running_names=list(running_names),
            )
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `uv run pytest tests/test_service.py -q`
Expected: PASS with streaming-event coverage added on top of the existing list-based usage tests.

- [ ] **Step 5: Commit the progress-event service changes**

```bash
git add src/codex_auth/models.py src/codex_auth/service.py tests/test_service.py
git commit -m "feat: add usage progress events"
```

### Task 2: Add Live TTY Rendering with Dynamic Ordering

**Files:**
- Modify: `src/codex_auth/cli.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Write the failing CLI tests for live status rendering and quota-priority ordering**

```python
def test_cli_usage_live_view_renders_running_and_queued_accounts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeStdout(io.StringIO):
        encoding = "utf-8"

        def isatty(self) -> bool:
            return True

    class FakeUsageService:
        def stream_usage_accounts(self):
            yield UsageBatchEvent(kind="phase", phase="prechecking network", queued_names=["alpha", "beta"], running_names=[])
            yield UsageBatchEvent(kind="phase", phase="querying", queued_names=["beta"], running_names=["alpha"])
            yield UsageBatchEvent(
                kind="account-finished",
                phase="querying",
                queued_names=[],
                running_names=["beta"],
                result=make_usage_result(
                    UsageQueryTarget(name="alpha", managed_state="managed", account_id="acct-alpha", raw={}, managed_name="alpha")
                ),
            )
            yield UsageBatchEvent(kind="phase", phase="completed", queued_names=[], running_names=[])

    fake_stdout = FakeStdout()
    monkeypatch.setattr("codex_auth.cli.sys.stdout", fake_stdout)
    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])

    assert result == 0
    rendered = fake_stdout.getvalue()
    assert "querying" in rendered
    assert "running: beta" in rendered
    assert "queued: -" in rendered


def test_sort_usage_results_orders_by_remaining_5h_then_weekly() -> None:
    low = make_usage_result(
        UsageQueryTarget(name="low", managed_state="managed", account_id="acct-low", raw={}, managed_name="low")
    )
    medium = make_usage_result(
        UsageQueryTarget(name="medium", managed_state="managed", account_id="acct-medium", raw={}, managed_name="medium")
    )
    high = make_usage_result(
        UsageQueryTarget(name="high", managed_state="managed", account_id="acct-high", raw={}, managed_name="high")
    )

    low.primary_window.used_percent = 95
    low.secondary_window.used_percent = 80
    medium.primary_window.used_percent = 40
    medium.secondary_window.used_percent = 30
    high.primary_window.used_percent = 10
    high.secondary_window.used_percent = 5

    ordered = _sort_usage_results([high, medium, low])

    assert [item.name for item in ordered] == ["low", "medium", "high"]
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: FAIL because the CLI only has one-shot rendering and no live event-driven view or quota-priority sort helper.

- [ ] **Step 3: Implement live redraw helpers and quota-priority result sorting**

```python
def _sort_usage_results(results: list[AccountUsageResult]) -> list[AccountUsageResult]:
    def remaining(window: UsageWindow | None) -> float:
        if window is None or window.remaining_percent is None:
            return 101.0
        return float(window.remaining_percent)

    errored = [result for result in results if result.error is not None]
    successful = [result for result in results if result.error is None]
    successful.sort(key=lambda result: (remaining(result.primary_window), remaining(result.secondary_window), result.name))
    errored.sort(key=lambda result: result.name)
    return errored + successful


def _render_usage_live_screen(
    *,
    phase: str,
    completed_results: list[AccountUsageResult],
    running_names: list[str],
    queued_names: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"phase: {phase}")
    lines.append("")
    for result in _sort_usage_results(completed_results):
        lines.extend(_render_usage_result(result))
        lines.append("")
    lines.append(f"running: {', '.join(running_names) if running_names else '-'}")
    lines.append(f"queued: {', '.join(queued_names) if queued_names else '-'}")
    return "\x1b[2J\x1b[H" + "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: PASS with live-view rendering, sort behavior, and existing non-TTY usage rendering tests green together.

- [ ] **Step 5: Commit the live renderer changes**

```bash
git add src/codex_auth/cli.py tests/test_cli_read_commands.py
git commit -m "feat: add live usage terminal view"
```

### Task 3: Preserve Plain-Text Fallback and Wire the Live View into `usage`

**Files:**
- Modify: `src/codex_auth/cli.py`
- Modify: `README.md`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Add a non-TTY regression test so redirected output stays plain text**

```python
def test_cli_usage_non_tty_keeps_plain_text_output(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeUsageService:
        def list_usage_accounts(self) -> list[AccountUsageResult]:
            return [
                make_usage_result(
                    UsageQueryTarget(name="alpha", managed_state="managed", account_id="acct-alpha", raw={}, managed_name="alpha")
                )
            ]

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 0
    assert "account: alpha" in captured.out
    assert "\x1b[2J" not in captured.out
```

- [ ] **Step 2: Run the CLI tests to verify the new fallback coverage fails**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: FAIL until the `usage` command chooses between live TTY rendering and the existing plain-text path.

- [ ] **Step 3: Dispatch bare `usage` to live or plain-text mode and document the behavior**

```python
if args.command == "usage":
    if args.name:
        result = service.get_usage_account(args.name)
        if result.error is not None:
            raise ValueError(result.error)
        for line in _render_usage_result(result):
            print(line)
        return 0

    if sys.stdout.isatty():
        return _run_live_usage_view(service)

    results = service.list_usage_accounts()
    ordered_results = _sort_usage_results(results)
    lines, any_success = _render_usage_results(ordered_results)
    for line in lines:
        print(line)
    return 0 if any_success else 1
```

```markdown
- `codex-auth usage` 在交互终端中会实时显示查询中的账号和已完成结果。
- 将输出重定向到文件或管道时，命令保持稳定的纯文本输出格式。
```

- [ ] **Step 4: Run focused live-view verification**

Run: `uv run pytest tests/test_service.py tests/test_cli_read_commands.py -q`
Expected: PASS with streaming service coverage, live TTY rendering tests, and plain-text fallback tests green together.

- [ ] **Step 5: Commit the mode-selection and README updates**

```bash
git add src/codex_auth/cli.py README.md tests/test_cli_read_commands.py
git commit -m "docs: describe live usage output"
```

### Task 4: Verify the End-to-End Change and Close the OpenSpec Task List

**Files:**
- Modify: `openspec/changes/add-account-usage-live-view/tasks.md`
- Test: `tests/test_usage_api.py`
- Test: `tests/test_service.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS with the repository suite green after the live-view path is added.

- [ ] **Step 2: Mark the OpenSpec task list complete**

```markdown
## 1. Progress Event Infrastructure

- [x] 1.1 Add usage batch progress-event models for queued, running, completed, and aborted states.
- [x] 1.2 Add a streaming batch query API that emits progress updates while preserving bounded concurrency.

## 2. Interactive Live View

- [x] 2.1 Render a bottom status area that shows the current phase plus running and queued accounts.
- [x] 2.2 Insert completed results into the top area as they finish.
- [x] 2.3 Sort completed successful results by remaining 5-hour quota, then weekly quota, with errors kept visible first.

## 3. Fallback and Verification

- [x] 3.1 Preserve non-TTY plain-text output.
- [x] 3.2 Run focused usage-related tests.
- [x] 3.3 Run the full `uv run pytest -q` suite.
```

- [ ] **Step 3: Commit the verification and task updates**

```bash
git add openspec/changes/add-account-usage-live-view/tasks.md
git commit -m "test: verify live usage view"
```
