import json

import pytest

from codex_auth.store import AccountStore


def make_snapshot(account_id: str) -> dict[str, object]:
    return {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
            "account_id": account_id,
        },
    }


def test_save_snapshot_writes_account_file_and_registry(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    snapshot_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    registry_path = tmp_path / ".codex-account-switcher" / "registry.json"

    assert snapshot_path.exists()
    registry = json.loads(registry_path.read_text())
    assert registry["active_name"] == "work"
    assert registry["accounts"]["work"]["account_id"] == "acct-work"


def test_remove_active_snapshot_requires_force_current(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    with pytest.raises(ValueError, match="currently active"):
        store.remove_snapshot("work", force_current=False)


def test_matched_active_name_returns_none_when_live_auth_has_drifted(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    store.write_live_auth(make_snapshot("acct-other"))

    assert store.matched_active_name() is None
