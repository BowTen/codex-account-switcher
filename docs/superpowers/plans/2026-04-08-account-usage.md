# Account Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `codex-auth usage [name]` so operators can inspect human-friendly 5-hour and weekly rate limits for managed accounts and the current unmanaged live account, with automatic token refresh when needed.

**Architecture:** Keep the current `argparse` CLI and service/store split. Add one focused module for ChatGPT usage API calls and one focused module for token expiry and refresh logic, then let the service layer assemble query targets, deduplicate the live account, persist refreshed tokens, and return render-ready usage results to the CLI.

**Tech Stack:** Python 3.12, `uv`, `pytest`, stdlib `urllib.request`, stdlib `json`, stdlib `base64`, existing `argparse` CLI

---

### Task 1: Add Usage Models and Network Primitives

**Files:**
- Modify: `src/codex_auth/models.py`
- Create: `src/codex_auth/token_refresh.py`
- Create: `src/codex_auth/usage_api.py`
- Test: `tests/test_usage_api.py`

- [ ] **Step 1: Write the failing usage API and token refresh tests**

```python
import json
from urllib.error import HTTPError

import pytest

from codex_auth.token_refresh import parse_access_token_expiry, refresh_chatgpt_tokens
from codex_auth.usage_api import fetch_usage_payload, parse_usage_payload


def test_parse_usage_payload_reads_primary_and_secondary_windows() -> None:
    payload = {
        "plan_type": "plus",
        "rate_limit": {
            "primary_window": {"used_percent": 7, "limit_window_seconds": 18000, "reset_at": 1775505971},
            "secondary_window": {"used_percent": 30, "limit_window_seconds": 604800, "reset_at": 1776049573},
        },
        "credits": {"has_credits": False, "unlimited": False, "balance": "0"},
    }

    result = parse_usage_payload(payload)

    assert result.plan_type == "plus"
    assert result.primary_window.used_percent == 7
    assert result.secondary_window.limit_window_seconds == 604800


def test_parse_usage_payload_allows_missing_rate_limit() -> None:
    result = parse_usage_payload({"plan_type": "plus", "credits": {"has_credits": False, "unlimited": False}})
    assert result.primary_window is None
    assert result.secondary_window is None


def test_refresh_chatgpt_tokens_replaces_returned_fields(monkeypatch) -> None:
    def fake_post(url: str, form_data: dict[str, str]) -> dict[str, str]:
        assert url == "https://auth.openai.com/oauth/token"
        assert form_data["grant_type"] == "refresh_token"
        assert form_data["refresh_token"] == "refresh-old"
        return {
            "access_token": "access-new",
            "refresh_token": "refresh-new",
            "id_token": "id-new",
        }

    monkeypatch.setattr("codex_auth.token_refresh.post_oauth_form", fake_post)

    refreshed = refresh_chatgpt_tokens(
        access_token="access-old",
        refresh_token="refresh-old",
        id_token="id-old",
        account_id="acct-old",
    )

    assert refreshed.access_token == "access-new"
    assert refreshed.refresh_token == "refresh-new"
    assert refreshed.id_token == "id-new"


def test_fetch_usage_payload_surfaces_http_errors(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):
        raise HTTPError("https://chatgpt.com/backend-api/wham/usage", 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("codex_auth.usage_api.perform_get_json", fake_get)

    with pytest.raises(ValueError, match="Usage request failed: HTTP 401"):
        fetch_usage_payload(access_token="token", account_id="acct-123")
```

- [ ] **Step 2: Run the usage API tests to verify they fail**

Run: `uv run pytest tests/test_usage_api.py -q`
Expected: FAIL with import errors because `codex_auth.token_refresh` and `codex_auth.usage_api` do not exist yet.

- [ ] **Step 3: Add minimal usage and refresh dataclasses**

```python
@dataclass(slots=True)
class UsageWindow:
    used_percent: float
    limit_window_seconds: int | None
    reset_at: int | None


@dataclass(slots=True)
class UsageSnapshot:
    plan_type: str | None
    primary_window: UsageWindow | None
    secondary_window: UsageWindow | None
    credits_balance: str | None
    has_credits: bool | None
    unlimited_credits: bool | None


@dataclass(slots=True)
class TokenRefreshResult:
    access_token: str
    refresh_token: str
    id_token: str
    account_id: str | None
```

- [ ] **Step 4: Implement the minimal token refresh module**

```python
TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
EXPIRY_SKEW_SECONDS = 60


def token_expired_or_near_expiry(access_token: str, *, now: datetime | None = None) -> bool:
    expiry = parse_access_token_expiry(access_token)
    if expiry is None:
        return False
    current = now or datetime.now(UTC)
    return expiry <= current + timedelta(seconds=EXPIRY_SKEW_SECONDS)


def refresh_chatgpt_tokens(*, access_token: str, refresh_token: str, id_token: str, account_id: str | None) -> TokenRefreshResult:
    payload = post_oauth_form(
        TOKEN_ENDPOINT,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
    )
    return TokenRefreshResult(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token", refresh_token),
        id_token=payload.get("id_token", id_token),
        account_id=extract_account_id_from_id_token(payload.get("id_token", id_token)) or account_id,
    )
```

- [ ] **Step 5: Implement the minimal usage API module**

```python
USAGE_ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
CODEX_USER_AGENT = "codex-cli/1.0.0"


def fetch_usage_payload(*, access_token: str, account_id: str) -> dict[str, Any]:
    try:
        return perform_get_json(
            USAGE_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": CODEX_USER_AGENT,
                "chatgpt-account-id": account_id,
            },
        )
    except HTTPError as exc:
        raise ValueError(f"Usage request failed: HTTP {exc.code}") from exc


def parse_usage_payload(payload: dict[str, Any]) -> UsageSnapshot:
    rate_limit = payload.get("rate_limit") or {}
    credits = payload.get("credits") or {}
    return UsageSnapshot(
        plan_type=payload.get("plan_type"),
        primary_window=build_usage_window(rate_limit.get("primary_window")),
        secondary_window=build_usage_window(rate_limit.get("secondary_window")),
        credits_balance=credits.get("balance"),
        has_credits=credits.get("has_credits"),
        unlimited_credits=credits.get("unlimited"),
    )
```

- [ ] **Step 6: Run the usage API tests to verify they pass**

Run: `uv run pytest tests/test_usage_api.py -q`
Expected: PASS with `4 passed`.

- [ ] **Step 7: Commit the network primitives**

```bash
git add src/codex_auth/models.py src/codex_auth/token_refresh.py src/codex_auth/usage_api.py tests/test_usage_api.py
git commit -m "feat: add usage api and token refresh primitives"
```

### Task 2: Add Store and Service Usage Query Support

**Files:**
- Modify: `src/codex_auth/models.py`
- Modify: `src/codex_auth/store.py`
- Modify: `src/codex_auth/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests for managed, unmanaged, deduped, and refreshed usage queries**

```python
def test_list_usage_accounts_includes_unmanaged_live_account(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.write_live_auth(make_snapshot("acct-live"))

    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: AccountUsageResult(
            name=target.name,
            managed_state=target.managed_state,
            account_id=target.account_id,
            plan_type="plus",
            primary_window=UsageWindow(used_percent=7, limit_window_seconds=18000, reset_at=1775505971),
            secondary_window=UsageWindow(used_percent=30, limit_window_seconds=604800, reset_at=1776049573),
            credits_balance="0",
            has_credits=False,
            unlimited_credits=False,
            refreshed=False,
            error=None,
        ),
    )

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["live", "work"]
    assert results[0].managed_state == "unmanaged"


def test_list_usage_accounts_deduplicates_matching_live_account(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    raw = make_snapshot("acct-work")
    service.store.save_snapshot("work", raw, force=False, mark_active=True)
    service.store.write_live_auth(raw)
    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", lambda target: make_usage_result(target))

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["work"]


def test_get_usage_account_persists_refreshed_managed_tokens(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: make_usage_result(target, refreshed=True, refreshed_raw=make_snapshot("acct-work-new")),
    )

    result = service.get_usage_account("work")

    assert result.refreshed is True
    assert service.store.load_snapshot("work").raw["tokens"]["account_id"] == "acct-work-new"


def test_get_usage_account_syncs_live_auth_for_current_account(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    raw = make_snapshot("acct-work")
    service.store.save_snapshot("work", raw, force=False, mark_active=True)
    service.store.write_live_auth(raw)

    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: make_usage_result(target, refreshed=True, refreshed_raw=make_snapshot("acct-work-new")),
    )

    service.get_usage_account("work")

    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-work-new"
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `uv run pytest tests/test_service.py -q`
Expected: FAIL with missing usage dataclasses, missing service methods, and missing refresh persistence support.

- [ ] **Step 3: Add query-target and query-result models**

```python
@dataclass(slots=True)
class UsageQueryTarget:
    name: str
    managed_state: str
    account_id: str
    raw: dict[str, Any]
    managed_name: str | None = None


@dataclass(slots=True)
class AccountUsageResult:
    name: str
    managed_state: str
    account_id: str
    plan_type: str | None
    primary_window: UsageWindow | None
    secondary_window: UsageWindow | None
    credits_balance: str | None
    has_credits: bool | None
    unlimited_credits: bool | None
    refreshed: bool
    refreshed_raw: dict[str, Any] | None
    error: str | None
```

- [ ] **Step 4: Add minimal store helpers for refresh persistence**

```python
def overwrite_snapshot(self, name: str, raw: dict[str, Any]) -> AccountMetadata:
    return self.save_snapshot(name, raw, force=True, mark_active=False)


def live_matches_snapshot(self, raw: dict[str, Any]) -> bool:
    current = self.read_live_auth()
    if current is None:
        return False
    return parse_snapshot(current).account_id == parse_snapshot(raw).account_id
```

- [ ] **Step 5: Implement service target selection and persistence flow**

```python
def get_usage_account(self, name: str) -> AccountUsageResult:
    target = self._build_managed_usage_target(name)
    result = fetch_account_usage_snapshot(target)
    self._persist_usage_refresh(target, result)
    return result


def list_usage_accounts(self) -> list[AccountUsageResult]:
    results: list[AccountUsageResult] = []
    for target in self._list_usage_targets():
        result = fetch_account_usage_snapshot(target)
        self._persist_usage_refresh(target, result)
        results.append(result)
    return results


def _persist_usage_refresh(self, target: UsageQueryTarget, result: AccountUsageResult) -> None:
    if not result.refreshed or result.refreshed_raw is None:
        return
    if target.managed_name is not None:
        self.store.overwrite_snapshot(target.managed_name, result.refreshed_raw)
    if self.store.live_matches_snapshot(target.raw):
        self.store.write_live_auth(result.refreshed_raw)
```

- [ ] **Step 6: Run the service tests to verify they pass**

Run: `uv run pytest tests/test_service.py -q`
Expected: PASS with existing switch/import tests plus the new usage tests.

- [ ] **Step 7: Commit the service-layer usage flow**

```bash
git add src/codex_auth/models.py src/codex_auth/store.py src/codex_auth/service.py tests/test_service.py
git commit -m "feat: add usage query service flow"
```

### Task 3: Add CLI Usage Command and Human-Friendly Rendering

**Files:**
- Modify: `src/codex_auth/cli.py`
- Modify: `README.md`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Write the failing CLI usage tests**

```python
def test_cli_usage_without_name_prints_managed_and_unmanaged_accounts(tmp_path, monkeypatch) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-live")))
    assert run_cli(tmp_path, "save", "work").returncode == 0

    monkeypatch.setattr(
        "codex_auth.cli.CodexAuthService.list_usage_accounts",
        lambda self: [
            make_cli_usage_result(name="live", managed_state="unmanaged", account_id="acct-live"),
            make_cli_usage_result(name="work", managed_state="managed", account_id="acct-work"),
        ],
    )

    result = run_cli(tmp_path, "usage")

    assert result.returncode == 0
    assert "live" in result.stdout
    assert "managed_state: unmanaged" not in result.stdout
    assert "5h limit:" in result.stdout
    assert "Weekly limit:" in result.stdout


def test_cli_usage_named_account_errors_cleanly(tmp_path) -> None:
    result = run_cli(tmp_path, "usage", "missing")
    assert result.returncode == 1
    assert "error: Unknown account: missing" in result.stderr
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: FAIL because the parser does not include `usage` and the CLI has no usage renderer.

- [ ] **Step 3: Add the `usage` subcommand and block renderer**

```python
usage_parser = subparsers.add_parser("usage", help="Show account rate limit usage.")
usage_parser.add_argument("name", nargs="?")
```

```python
def render_usage_result(result: AccountUsageResult) -> list[str]:
    lines = [f"{result.name} ({result.managed_state})"]
    if result.plan_type:
        lines.append(f"plan: {result.plan_type}")
    if result.error:
        lines.append(f"error: {result.error}")
        return lines
    lines.append(render_usage_line("5h limit", result.primary_window))
    lines.append(render_usage_line("Weekly limit", result.secondary_window))
    if result.refreshed:
        lines.append("token refreshed")
    return lines
```

- [ ] **Step 4: Wire the CLI command into the service**

```python
if args.command == "usage":
    results = [service.get_usage_account(args.name)] if args.name else service.list_usage_accounts()
    for index, result in enumerate(results):
        if index:
            print()
        for line in render_usage_result(result):
            print(line)
    return 0 if any(item.error is None for item in results) else 1
```

- [ ] **Step 5: Document the new command in the README**

```markdown
codex-auth usage
codex-auth usage work
```

```markdown
- 一键查询所有账号或指定账号的 5 小时和每周额度信息。
```

- [ ] **Step 6: Run the CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli_read_commands.py -q`
Expected: PASS with the new usage command coverage and the existing read-command coverage.

- [ ] **Step 7: Commit the CLI usage command**

```bash
git add src/codex_auth/cli.py README.md tests/test_cli_read_commands.py
git commit -m "feat: add account usage command"
```

### Task 4: Verify the Full Feature and Documentation

**Files:**
- Modify: `openspec/changes/<change-name>/tasks.md`
- Modify: `openspec/changes/<change-name>/specs/account-usage/spec.md`
- Test: `tests/test_usage_api.py`
- Test: `tests/test_service.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Run the focused usage test suite**

Run: `uv run pytest tests/test_usage_api.py tests/test_service.py tests/test_cli_read_commands.py -q`
Expected: PASS with all new usage tests green.

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS with the pre-existing suite and the new usage coverage green together.

- [ ] **Step 3: Mark the OpenSpec task list complete**

```markdown
## 1. Usage Query Implementation

- [x] 1.1 Add token refresh and ChatGPT usage API support for saved snapshots and the live auth file.
- [x] 1.2 Add service and CLI flows for `codex-auth usage [name]`.
- [x] 1.3 Add human-friendly output rendering and regression coverage.
```

- [ ] **Step 4: Commit the verification pass**

```bash
git add openspec/changes/<change-name>/tasks.md openspec/changes/<change-name>/specs/account-usage/spec.md tests/test_usage_api.py tests/test_service.py tests/test_cli_read_commands.py README.md src/codex_auth/cli.py src/codex_auth/models.py src/codex_auth/service.py src/codex_auth/store.py src/codex_auth/token_refresh.py src/codex_auth/usage_api.py
git commit -m "test: verify account usage command"
```
