import os
import stat
import threading
import time
from pathlib import Path

import pytest

from codex_auth import __version__
from codex_auth import service as service_module
from codex_auth.models import (
    AccountMetadata,
    AccountUsageResult,
    ImportPlanItem,
    TokenRefreshResult,
    TransferAccount,
    TransferArchive,
    UsageQueryTarget,
    UsageCredits,
    UsageWindow,
    UsageSnapshot,
)
from codex_auth.service import CodexAuthService
from codex_auth.validators import parse_snapshot


def write_fake_codex(bin_dir: Path, *, returncode: int = 0, output: str = "Logged in using ChatGPT\n") -> None:
    script = bin_dir / "codex"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"print({output!r}, end='')\n"
        f"raise SystemExit({returncode})\n"
    )
    script.chmod(0o755)


def make_snapshot(account_id: str) -> dict[str, object]:
    return {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": f"access-{account_id}",
            "refresh_token": f"refresh-{account_id}",
            "id_token": f"id-{account_id}",
            "account_id": account_id,
        },
    }


def make_snapshot_with_access_token(account_id: str, access_token: str) -> dict[str, object]:
    snapshot = make_snapshot(account_id)
    snapshot["tokens"]["access_token"] = access_token
    return snapshot


@pytest.fixture(autouse=True)
def stub_usage_preflight(monkeypatch) -> None:
    monkeypatch.setattr(service_module, "probe_usage_endpoint", lambda: None, raising=False)


def test_use_account_switches_live_auth_and_marks_verified(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir)

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    service = CodexAuthService(home=tmp_path, env=env)

    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-work"))

    result = service.use_account("personal")

    assert result.switched is True
    assert result.verified is True
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-personal"
    assert service.store.current_active_name() == "personal"


def test_failed_verification_keeps_target_as_current_managed_account(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, returncode=1, output="Not logged in\n")

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    service = CodexAuthService(home=tmp_path, env=env)

    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-work"))

    result = service.use_account("personal")

    assert result.switched is True
    assert result.verified is False
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-personal"
    assert service.store.current_active_name() == "personal"


def test_switching_away_after_failed_verification_saves_back_current_live_snapshot(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, returncode=1, output="Not logged in\n")

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    service = CodexAuthService(home=tmp_path, env=env)

    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-work"))

    first_result = service.use_account("personal")

    assert first_result.verified is False
    assert service.store.current_active_name() == "personal"

    updated_personal = make_snapshot_with_access_token("acct-personal", "access-personal-updated")
    service.store.write_live_auth(updated_personal)

    second_bin_dir = tmp_path / "bin2"
    second_bin_dir.mkdir()
    write_fake_codex(second_bin_dir)
    second_env = {**os.environ, "PATH": f"{second_bin_dir}:{os.environ['PATH']}"}
    second_service = CodexAuthService(home=tmp_path, env=second_env)

    second_result = second_service.use_account("work")

    assert second_result.verified is True
    assert second_service.store.read_live_auth()["tokens"]["account_id"] == "acct-work"
    assert second_service.store.current_active_name() == "work"
    assert second_service.store.load_snapshot("personal").raw["tokens"]["access_token"] == "access-personal-updated"


def test_missing_codex_executable_returns_partial_result(tmp_path) -> None:
    empty_bin_dir = tmp_path / "empty-bin"
    empty_bin_dir.mkdir()
    env = {**os.environ, "PATH": str(empty_bin_dir)}
    service = CodexAuthService(home=tmp_path, env=env)

    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-work"))

    result = service.use_account("personal")

    assert result.switched is True
    assert result.verified is False
    assert result.verification.ok is False
    assert "Could not find executable: codex" in result.verification.stderr
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-personal"
    assert service.store.current_active_name() == "personal"


def test_build_export_archive_includes_only_selected_accounts(tmp_path) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)

    archive = service.build_export_archive(["work"])

    assert [account.name for account in archive.accounts] == ["work"]
    assert archive.accounts[0].snapshot.raw["tokens"]["account_id"] == "acct-work"
    assert archive.exported_at is not None
    assert archive.tool_version == __version__


def test_write_export_archive_and_read_import_archive_round_trip(tmp_path) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    archive_path = tmp_path / "accounts-export.codex"

    service.write_export_archive(["work"], archive_path, passphrase="correct horse battery staple")
    restored = service.read_import_archive(archive_path, passphrase="correct horse battery staple")

    assert archive_path.exists()
    assert stat.S_IMODE(archive_path.stat().st_mode) == 0o600
    assert [account.name for account in restored.accounts] == ["work"]
    assert restored.accounts[0].metadata.account_id == "acct-work"
    assert restored.exported_at is not None


def test_write_export_archive_is_atomic_on_replace_failure(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    archive_path = tmp_path / "accounts-export.codex"

    original_replace = Path.replace

    def fail_replace(self: Path, target: Path):  # type: ignore[no-untyped-def]
        if target == archive_path:
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        service.write_export_archive(["work"], archive_path, passphrase="correct horse battery staple")

    assert not archive_path.exists()


def test_apply_import_archive_writes_selected_accounts_without_touching_live_auth(tmp_path) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-old-work"), force=False, mark_active=True)
    live_raw = make_snapshot("acct-live")
    service.store.write_live_auth(live_raw)
    active_before = service.store.current_active_name()

    work_account = TransferAccount(
        name="work",
        metadata=AccountMetadata(
            name="work",
            auth_mode="chatgpt",
            account_id="acct-new-work",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-02-02T00:00:00Z",
            last_refresh="2026-04-04T10:00:00Z",
            last_verified_at="2025-03-03T00:00:00Z",
        ),
        snapshot=parse_snapshot(make_snapshot("acct-new-work")),
    )
    travel_account = TransferAccount(
        name="travel",
        metadata=AccountMetadata(
            name="travel",
            auth_mode="chatgpt",
            account_id="acct-travel",
            created_at="2024-05-05T00:00:00Z",
            updated_at="2024-06-06T00:00:00Z",
            last_refresh="2026-04-04T10:00:00Z",
            last_verified_at="2024-07-07T00:00:00Z",
        ),
        snapshot=parse_snapshot(make_snapshot("acct-travel")),
    )
    archive = TransferArchive(
        exported_at="2026-04-05T10:00:00Z",
        tool_version="0.1.0",
        accounts=[work_account, travel_account],
    )
    plan = [
        ImportPlanItem(source_name="work", target_name="work", action="overwrite"),
        ImportPlanItem(source_name="travel", target_name="vacation", action="rename"),
    ]

    result = service.apply_import_archive(archive, plan)

    assert result.imported == ["work", "vacation"]
    assert service.store.load_snapshot("work").account_id == "acct-new-work"
    assert service.store.load_snapshot("vacation").account_id == "acct-travel"
    assert service.inspect_account("work")["created_at"] == "2025-01-01T00:00:00Z"
    assert service.inspect_account("work")["updated_at"] == "2025-02-02T00:00:00Z"
    assert service.inspect_account("work")["last_verified_at"] == "2025-03-03T00:00:00Z"
    assert service.inspect_account("vacation")["name"] == "vacation"
    assert service.inspect_account("vacation")["created_at"] == "2024-05-05T00:00:00Z"
    assert service.inspect_account("vacation")["updated_at"] == "2024-06-06T00:00:00Z"
    assert service.inspect_account("vacation")["last_verified_at"] == "2024-07-07T00:00:00Z"
    assert service.store.read_live_auth() == live_raw
    assert service.store.current_active_name() == active_before


def make_usage_result(
    target: UsageQueryTarget,
    *,
    refreshed: bool = False,
    refreshed_raw: dict[str, object] | None = None,
    error: str | None = None,
) -> AccountUsageResult:
    return AccountUsageResult(
        name=target.name,
        managed_state=target.managed_state,
        account_id=target.account_id,
        plan_type="plus",
        primary_window=UsageWindow(used_percent=7, limit_window_seconds=18000, reset_at=1775505971),
        secondary_window=UsageWindow(used_percent=30, limit_window_seconds=604800, reset_at=1776049573),
        credits_balance="0",
        has_credits=False,
        unlimited_credits=False,
        refreshed=refreshed,
        refreshed_raw=refreshed_raw,
        error=error,
    )


def test_list_usage_accounts_uses_noncolliding_live_display_name(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("live", make_snapshot("acct-managed-live"), force=False, mark_active=True)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-live"))

    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: make_usage_result(target),
    )

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["(live)", "live", "work"]
    assert results[0].managed_state == "unmanaged"
    assert results[1].managed_state == "managed"


def test_list_usage_accounts_deduplicates_matching_live_account(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    raw = make_snapshot("acct-work")
    service.store.save_snapshot("work", raw, force=False, mark_active=True)
    service.store.write_live_auth(raw)
    monkeypatch.setattr(
        "codex_auth.service.fetch_account_usage_snapshot",
        lambda target: make_usage_result(target),
    )

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


def test_get_usage_account_persists_refreshed_tokens_even_when_usage_fails(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    raw = make_snapshot("acct-work")
    service.store.save_snapshot("work", raw, force=False, mark_active=True)
    service.store.write_live_auth(raw)

    monkeypatch.setattr(service_module, "access_token_needs_refresh", lambda access_token: True, raising=False)
    monkeypatch.setattr(
        service_module,
        "refresh_chatgpt_credentials",
        lambda **kwargs: TokenRefreshResult(
            access_token="access-work-new",
            refresh_token="refresh-work-new",
            id_token="id-work-new",
            account_id="acct-work-new",
            expires_in=3600,
            expires_at="2026-04-08T10:00:00Z",
            raw={"ok": True},
        ),
        raising=False,
    )
    monkeypatch.setattr(
        service_module,
        "fetch_usage",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("usage failed")),
        raising=False,
    )

    result = service.get_usage_account("work")

    assert result.error == "usage failed"
    assert result.refreshed is True
    assert result.refreshed_raw is not None
    assert service.store.load_snapshot("work").raw["tokens"]["account_id"] == "acct-work-new"
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-work-new"


def test_get_usage_account_queries_only_named_managed_account(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("travel", make_snapshot("acct-travel"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-live"))

    queried: list[str] = []

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        queried.append(target.name)
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    result = service.get_usage_account("work")

    assert result.name == "work"
    assert queried == ["work"]


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


def test_fetch_account_usage_snapshot_refreshes_near_expiry_tokens(tmp_path, monkeypatch) -> None:
    raw = make_snapshot("acct-work")
    target = UsageQueryTarget(
        name="work",
        managed_state="managed",
        account_id="acct-work",
        raw=raw,
        managed_name="work",
    )

    monkeypatch.setattr(service_module, "access_token_needs_refresh", lambda access_token: True, raising=False)

    refresh_calls: list[tuple[str, str, str, str]] = []

    def fake_refresh(*, access_token: str, refresh_token: str, id_token: str, account_id: str):
        refresh_calls.append((access_token, refresh_token, id_token, account_id))
        return TokenRefreshResult(
            access_token="access-work-new",
            refresh_token="refresh-work-new",
            id_token="id-work-new",
            account_id="acct-work-new",
            expires_in=3600,
            expires_at="2026-04-08T10:00:00Z",
            raw={"ok": True},
        )

    usage_calls: list[tuple[str, str]] = []

    def fake_fetch_usage(*, access_token: str, account_id: str):
        usage_calls.append((access_token, account_id))
        return UsageSnapshot(
            account_id=account_id,
            plan_type="plus",
            primary_window=UsageWindow(used_percent=5, limit_window_seconds=18000, reset_at=1775505971),
            secondary_window=UsageWindow(used_percent=15, limit_window_seconds=604800, reset_at=1776049573),
            credits=UsageCredits(has_credits=True, unlimited=False, balance="12.50"),
            raw={"plan_type": "plus"},
        )

    monkeypatch.setattr(service_module, "refresh_chatgpt_credentials", fake_refresh, raising=False)
    monkeypatch.setattr(service_module, "fetch_usage", fake_fetch_usage, raising=False)

    result = service_module.fetch_account_usage_snapshot(target)

    assert refresh_calls == [("access-acct-work", "refresh-acct-work", "id-acct-work", "acct-work")]
    assert usage_calls == [("access-work-new", "acct-work-new")]
    assert result.refreshed is True
    assert result.refreshed_raw is not None
    assert result.refreshed_raw["tokens"]["access_token"] == "access-work-new"
    assert result.refreshed_raw["tokens"]["refresh_token"] == "refresh-work-new"
    assert result.refreshed_raw["tokens"]["id_token"] == "id-work-new"
    assert result.refreshed_raw["tokens"]["account_id"] == "acct-work-new"
    assert result.refreshed_raw["last_refresh"] == "2026-04-08T10:00:00Z"
    assert result.credits_balance == "12.50"
    assert result.has_credits is True
    assert result.unlimited_credits is False


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


def test_list_usage_accounts_continues_after_per_account_failure(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("travel", make_snapshot("acct-travel"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-live"))

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        if target.name == "travel":
            raise ValueError("usage failed")
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["(live)", "travel", "work"]
    assert results[1].error == "usage failed"
    assert results[0].error is None


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


def test_list_usage_accounts_limits_concurrent_fetches_to_four(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    for index in range(6):
        service.store.save_snapshot(
            f"account-{index}",
            make_snapshot(f"acct-{index}"),
            force=False,
            mark_active=index == 0,
        )

    active_fetches = 0
    peak_fetches = 0
    lock = threading.Lock()

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        nonlocal active_fetches, peak_fetches
        with lock:
            active_fetches += 1
            peak_fetches = max(peak_fetches, active_fetches)
        try:
            time.sleep(0.05)
            return make_usage_result(target)
        finally:
            with lock:
                active_fetches -= 1

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    results = service.list_usage_accounts()

    assert [item.name for item in results] == [f"account-{index}" for index in range(6)]
    assert peak_fetches == 4


def test_list_usage_accounts_returns_deterministic_order_when_completion_order_differs(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    for name, account_id in [("alpha", "acct-alpha"), ("beta", "acct-beta"), ("gamma", "acct-gamma")]:
        service.store.save_snapshot(name, make_snapshot(account_id), force=False, mark_active=name == "alpha")

    completion_order: list[str] = []
    lock = threading.Lock()

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        delays = {"alpha": 0.2, "beta": 0.05, "gamma": 0.1}
        time.sleep(delays[target.name])
        with lock:
            completion_order.append(target.name)
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    results = service.list_usage_accounts()
    returned_order = [item.name for item in results]

    assert returned_order == ["alpha", "beta", "gamma"]
    assert completion_order != returned_order


def test_list_usage_accounts_persists_refreshed_results_in_target_order(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    for name, account_id in [("alpha", "acct-alpha"), ("beta", "acct-beta"), ("gamma", "acct-gamma")]:
        service.store.save_snapshot(name, make_snapshot(account_id), force=False, mark_active=name == "alpha")

    barrier = threading.Barrier(4)
    release_events = {name: threading.Event() for name in ["alpha", "beta", "gamma"]}
    completed_events = {name: threading.Event() for name in ["alpha", "beta", "gamma"]}
    completion_order: list[str] = []
    persistence_order: list[str] = []
    controller_errors: list[str] = []
    order_lock = threading.Lock()

    def controller() -> None:
        try:
            barrier.wait()
            for name in ["beta", "gamma", "alpha"]:
                release_events[name].set()
                if not completed_events[name].wait(timeout=1.0):
                    raise AssertionError(f"{name} fetch did not complete")
        except Exception as exc:  # noqa: BLE001
            controller_errors.append(str(exc))

    controller_thread = threading.Thread(target=controller, daemon=True)
    controller_thread.start()

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        barrier.wait()
        if not release_events[target.name].wait(timeout=1.0):
            raise AssertionError(f"{target.name} fetch was not released")
        with order_lock:
            completion_order.append(target.name)
        completed_events[target.name].set()
        return make_usage_result(
            target,
            refreshed=True,
            refreshed_raw=make_snapshot(f"{target.account_id}-refreshed"),
        )

    original_persist = service._persist_usage_refresh

    def record_persist(target: UsageQueryTarget, result: AccountUsageResult) -> None:
        with order_lock:
            persistence_order.append(target.name)
        original_persist(target, result)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)
    monkeypatch.setattr(service, "_persist_usage_refresh", record_persist)

    results = service.list_usage_accounts()
    controller_thread.join(timeout=1.0)

    assert controller_thread.is_alive() is False
    assert controller_errors == []
    assert completion_order == ["beta", "gamma", "alpha"]
    assert persistence_order == ["alpha", "beta", "gamma"]
    assert [item.name for item in results] == ["alpha", "beta", "gamma"]


def test_list_usage_accounts_continues_when_a_concurrent_fetch_fails(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    for name, account_id in [("alpha", "acct-alpha"), ("beta", "acct-beta"), ("gamma", "acct-gamma")]:
        service.store.save_snapshot(name, make_snapshot(account_id), force=False, mark_active=name == "alpha")

    beta_failed = threading.Event()

    def fake_fetch(target: UsageQueryTarget) -> AccountUsageResult:
        if target.name == "beta":
            beta_failed.set()
            raise ValueError("usage failed")
        if not beta_failed.wait(timeout=1.0):
            raise AssertionError("beta fetch did not start")
        return make_usage_result(target)

    monkeypatch.setattr("codex_auth.service.fetch_account_usage_snapshot", fake_fetch)

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["alpha", "beta", "gamma"]
    assert results[0].error is None
    assert results[1].error == "usage failed"
    assert results[2].error is None


def test_list_usage_accounts_continues_when_managed_snapshot_is_malformed(tmp_path, monkeypatch) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("broken", make_snapshot("acct-broken"), force=False, mark_active=True)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=False)
    service.store.accounts_dir.joinpath("broken.json").write_text("{broken json")

    monkeypatch.setattr(service_module, "access_token_needs_refresh", lambda access_token: False, raising=False)
    monkeypatch.setattr(
        service_module,
        "fetch_usage",
        lambda **kwargs: UsageSnapshot(
            account_id=kwargs["account_id"],
            plan_type="plus",
            primary_window=UsageWindow(used_percent=7, limit_window_seconds=18000, reset_at=1775505971),
            secondary_window=UsageWindow(used_percent=30, limit_window_seconds=604800, reset_at=1776049573),
            credits=UsageCredits(has_credits=False, unlimited=False, balance="0"),
            raw={"plan_type": "plus"},
        ),
        raising=False,
    )

    results = service.list_usage_accounts()

    assert [item.name for item in results] == ["broken", "work"]
    assert results[0].error is not None
    assert results[1].error is None
