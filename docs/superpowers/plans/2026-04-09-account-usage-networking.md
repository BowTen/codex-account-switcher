# Account Usage Networking Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `codex-auth usage` fail fast and clearly when the usage endpoint is unreachable or a usage request times out.

**Architecture:** Keep transport concerns in `src/codex_auth/usage_api.py`, add typed usage-network errors in `src/codex_auth/errors.py`, and enforce batch timeout semantics in `src/codex_auth/service.py`. The CLI should stay thin and continue surfacing concise command-level errors while the service distinguishes timeout aborts from ordinary per-account failures.

**Tech Stack:** Python 3.12, `uv`, `pytest`, stdlib `urllib`, stdlib `socket`, existing argparse CLI

---

### Task 1: Add Usage Endpoint Preflight and Timeout Error Types

**Files:**
- Modify: `src/codex_auth/errors.py`
- Modify: `src/codex_auth/usage_api.py`
- Test: `tests/test_usage_api.py`

- [ ] **Step 1: Write the failing usage API tests for preflight reachability and timeout mapping**

```python
def test_probe_usage_endpoint_treats_http_error_as_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_auth import usage_api

    class Response:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

    def fake_urlopen(request, timeout=None):
        raise usage_api.urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=Response(401, b'{"error":"unauthorized"}'),
        )

    monkeypatch.setattr(usage_api.urllib.request, "urlopen", fake_urlopen)

    usage_api.probe_usage_endpoint()


def test_probe_usage_endpoint_raises_concise_network_error_for_unreachable_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_auth import usage_api
    from codex_auth.errors import UsageNetworkError

    def fake_urlopen(request, timeout=None):
        raise usage_api.urllib.error.URLError("network is unreachable")

    monkeypatch.setattr(usage_api.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(UsageNetworkError, match="usage endpoint unreachable: network is unreachable"):
        usage_api.probe_usage_endpoint()


def test_fetch_usage_raises_usage_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_auth import usage_api
    from codex_auth.errors import UsageTimeoutError

    def fake_urlopen(request, timeout=None):
        raise usage_api.urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(usage_api.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(UsageTimeoutError, match="usage request timed out"):
        usage_api.fetch_usage(access_token="token", account_id="acct-123")
```

- [ ] **Step 2: Run the usage API tests to verify they fail**

Run: `uv run pytest tests/test_usage_api.py -q`
Expected: FAIL because there is no preflight probe and usage transport failures still collapse into generic `ValueError`.

- [ ] **Step 3: Implement typed usage-network errors and preflight probing**

```python
class UsageNetworkError(ValueError):
    pass


class UsageTimeoutError(ValueError):
    pass


USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
DEFAULT_USAGE_TIMEOUT_SECONDS = 10.0


def probe_usage_endpoint(
    *,
    opener: Callable[..., Any] | None = None,
    timeout: float = DEFAULT_USAGE_TIMEOUT_SECONDS,
) -> None:
    req = urllib.request.Request(USAGE_URL, method="GET")
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=timeout):
            return None
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError as exc:
        if _is_timeout_reason(exc.reason):
            raise UsageTimeoutError("usage endpoint probe timed out") from None
        raise UsageNetworkError(f"usage endpoint unreachable: {exc.reason}") from None


def fetch_usage(
    *,
    access_token: str,
    account_id: str,
    opener: Callable[..., Any] | None = None,
    timeout: float = DEFAULT_USAGE_TIMEOUT_SECONDS,
) -> UsageSnapshot:
    req = urllib.request.Request(USAGE_URL, method="GET")
    req.add_header("authorization", f"Bearer {access_token}")
    req.add_header("chatgpt-account-id", account_id)
    req.add_header("user-agent", "codex-cli/1.0.0")
    req.add_header("accept", "application/json")

    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"usage request failed: {exc.code} {exc.reason}") from None
    except urllib.error.URLError as exc:
        if _is_timeout_reason(exc.reason):
            raise UsageTimeoutError("usage request timed out") from None
        raise ValueError(f"usage request failed: {exc.reason}") from None
```

- [ ] **Step 4: Run the usage API tests to verify they pass**

Run: `uv run pytest tests/test_usage_api.py -q`
Expected: PASS with preflight and timeout coverage green alongside the existing payload parsing tests.

- [ ] **Step 5: Commit the transport-layer changes**

```bash
git add src/codex_auth/errors.py src/codex_auth/usage_api.py tests/test_usage_api.py
git commit -m "feat: harden usage network handling"
```

### Task 2: Enforce Batch Timeout Abort Semantics in the Service Layer

**Files:**
- Modify: `src/codex_auth/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests for preflight gating and batch timeout aborts**

```python
def test_list_usage_accounts_runs_preflight_before_fetching_targets(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    events: list[str] = []

    monkeypatch.setattr("codex_auth.service.probe_usage_endpoint", lambda: events.append("probe"))
    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: events.append(target.name) or make_usage_result(target),
    )

    service.list_usage_accounts()

    assert events == ["probe", "work"]


def test_list_usage_accounts_aborts_batch_when_one_account_times_out(tmp_path, monkeypatch) -> None:
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

    with pytest.raises(UsageTimeoutError, match="usage request timed out"):
        service.list_usage_accounts()


def test_list_usage_accounts_continues_for_non_timeout_account_errors(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("alpha", make_snapshot("acct-alpha"), force=False, mark_active=True)
    service.store.save_snapshot("beta", make_snapshot("acct-beta"), force=False, mark_active=False)

    monkeypatch.setattr("codex_auth.service.probe_usage_endpoint", lambda: None)

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        if target.name == "alpha":
            return make_usage_result(target, error="usage request failed: 429 Too Many Requests")
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    results = service.list_usage_accounts()

    assert results[0].error == "usage request failed: 429 Too Many Requests"
    assert results[1].error is None
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `uv run pytest tests/test_service.py -q`
Expected: FAIL because `list_usage_accounts()` does not preflight first and currently converts all worker exceptions into per-account results instead of aborting on timeouts.

- [ ] **Step 3: Implement preflight gating and timeout-aware batch abort logic**

```python
def get_usage_account(self, name: str) -> AccountUsageResult:
    probe_usage_endpoint()
    target = self._build_managed_usage_target(name)
    result = self._fetch_usage_target(target)
    self._persist_usage_refresh(target, result)
    return result


def list_usage_accounts(self) -> list[AccountUsageResult]:
    probe_usage_endpoint()
    targets = self._list_usage_targets()
    results: list[AccountUsageResult | None] = [None] * len(targets)
    completed: dict[int, tuple[UsageQueryTarget, AccountUsageResult]] = {}
    next_flush_index = 0

    with ThreadPoolExecutor(max_workers=USAGE_BATCH_MAX_WORKERS) as executor:
        futures = {
            executor.submit(self._fetch_usage_target, target): (index, target)
            for index, target in enumerate(targets)
        }
        for future in as_completed(futures):
            index, target = futures[future]
            try:
                result = future.result()
            except UsageTimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            except Exception as exc:  # noqa: BLE001
                result = self._usage_fetch_error_result(target, exc)
            completed[index] = (target, result)
            while next_flush_index in completed:
                flush_target, flush_result = completed.pop(next_flush_index)
                self._persist_usage_refresh(flush_target, flush_result)
                results[next_flush_index] = flush_result
                next_flush_index += 1

    return [result for result in results if result is not None]
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `uv run pytest tests/test_service.py -q`
Expected: PASS with the new timeout-abort semantics, preflight ordering checks, and existing refresh-persistence coverage green.

- [ ] **Step 5: Commit the service-layer changes**

```bash
git add src/codex_auth/service.py tests/test_service.py
git commit -m "feat: abort usage batches on timeout"
```

### Task 3: Verify CLI Error Surfacing and Complete the Change

**Files:**
- Modify: `tests/test_cli_read_commands.py`
- Modify: `openspec/changes/harden-account-usage-networking/tasks.md`
- Test: `tests/test_usage_api.py`
- Test: `tests/test_service.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Add CLI tests for concise preflight and timeout failures**

```python
def test_cli_usage_reports_preflight_network_failure(tmp_path, monkeypatch, capsys) -> None:
    from codex_auth.errors import UsageNetworkError

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeUsageService:
        def list_usage_accounts(self):
            raise UsageNetworkError("usage endpoint unreachable: network is unreachable")

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 1
    assert "error: usage endpoint unreachable: network is unreachable" in captured.err


def test_cli_usage_reports_timeout_failure(tmp_path, monkeypatch, capsys) -> None:
    from codex_auth.errors import UsageTimeoutError

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeUsageService:
        def list_usage_accounts(self):
            raise UsageTimeoutError("usage request timed out")

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 1
    assert "error: usage request timed out" in captured.err
```

- [ ] **Step 2: Run focused networking-related usage tests**

Run: `uv run pytest tests/test_usage_api.py tests/test_service.py tests/test_cli_read_commands.py -q`
Expected: PASS with transport, service, and CLI failure-surfacing behavior green together.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS with the full repository suite green after the new timeout and preflight semantics land.

- [ ] **Step 4: Mark the OpenSpec task list complete**

```markdown
## 1. Transport Hardening

- [x] 1.1 Add a usage endpoint preflight probe that distinguishes reachability failures from reachable HTTP responses.
- [x] 1.2 Add explicit timeout mapping for usage requests.

## 2. Command Semantics

- [x] 2.1 Run preflight before named and batch usage queries.
- [x] 2.2 Abort a batch usage query when any account request times out.
- [x] 2.3 Preserve per-account continuation for non-timeout failures.

## 3. Verification

- [x] 3.1 Add CLI coverage for network-preflight and timeout failures.
- [x] 3.2 Run focused usage-related tests.
- [x] 3.3 Run the full `uv run pytest -q` suite.
```

- [ ] **Step 5: Commit the verification and task updates**

```bash
git add tests/test_cli_read_commands.py openspec/changes/harden-account-usage-networking/tasks.md
git commit -m "test: cover usage networking failures"
```
