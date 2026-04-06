import json

import pytest

from codex_auth.models import ImportPlanItem, TransferAccount
from codex_auth.store import AccountStore
from codex_auth.validators import build_metadata, parse_snapshot


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


def test_matched_active_name_returns_none_when_live_auth_is_malformed(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    store.live_auth_path.parent.mkdir(parents=True, exist_ok=True)
    store.live_auth_path.write_text("{not json")

    assert store.matched_active_name() is None


def test_save_snapshot_rolls_back_snapshot_file_when_registry_write_fails(tmp_path, monkeypatch) -> None:
    store = AccountStore(tmp_path)

    def fail_registry_write(path, payload):  # type: ignore[no-untyped-def]
        if path == store.registry_path:
            raise OSError("registry write failed")
        store._write_json_atomic_original(path, payload)

    store._write_json_atomic_original = store._write_json_atomic  # type: ignore[attr-defined]
    monkeypatch.setattr(store, "_write_json_atomic", fail_registry_write)

    with pytest.raises(OSError, match="registry write failed"):
        store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    assert not (tmp_path / ".codex-account-switcher" / "accounts" / "work.json").exists()
    assert not (tmp_path / ".codex-account-switcher" / "registry.json").exists()


def test_save_snapshot_force_over_existing_snapshot_restores_previous_file_on_registry_failure(
    tmp_path, monkeypatch
) -> None:
    store = AccountStore(tmp_path)
    original_snapshot = make_snapshot("acct-old")
    updated_snapshot = make_snapshot("acct-new")
    store.save_snapshot("work", original_snapshot, force=False, mark_active=True)
    snapshot_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    original_text = snapshot_path.read_text()

    def fail_registry_write(path, payload):  # type: ignore[no-untyped-def]
        if path == store.registry_path:
            raise OSError("registry write failed")
        store._write_json_atomic_original(path, payload)

    store._write_json_atomic_original = store._write_json_atomic  # type: ignore[attr-defined]
    monkeypatch.setattr(store, "_write_json_atomic", fail_registry_write)

    with pytest.raises(OSError, match="registry write failed"):
        store.save_snapshot("work", updated_snapshot, force=True, mark_active=True)

    assert snapshot_path.read_text() == original_text
    registry_path = tmp_path / ".codex-account-switcher" / "registry.json"
    registry = json.loads(registry_path.read_text())
    assert registry["active_name"] == "work"
    assert registry["accounts"]["work"]["account_id"] == "acct-old"


def test_remove_snapshot_rolls_back_deleted_file_when_registry_write_fails(tmp_path, monkeypatch) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    snapshot_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    original_snapshot = snapshot_path.read_text()

    def fail_registry_write(path, payload):  # type: ignore[no-untyped-def]
        if path == store.registry_path:
            raise OSError("registry write failed")
        store._write_json_atomic_original(path, payload)

    store._write_json_atomic_original = store._write_json_atomic  # type: ignore[attr-defined]
    monkeypatch.setattr(store, "_write_json_atomic", fail_registry_write)

    with pytest.raises(OSError, match="registry write failed"):
        store.remove_snapshot("work", force_current=True)

    assert snapshot_path.exists()
    assert snapshot_path.read_text() == original_snapshot


def test_rename_snapshot_rolls_back_renamed_file_when_registry_write_fails(tmp_path, monkeypatch) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    old_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    original_snapshot = old_path.read_text()
    new_path = tmp_path / ".codex-account-switcher" / "accounts" / "new.json"

    def fail_registry_write(path, payload):  # type: ignore[no-untyped-def]
        if path == store.registry_path:
            raise OSError("registry write failed")
        store._write_json_atomic_original(path, payload)

    store._write_json_atomic_original = store._write_json_atomic  # type: ignore[attr-defined]
    monkeypatch.setattr(store, "_write_json_atomic", fail_registry_write)

    with pytest.raises(OSError, match="registry write failed"):
        store.rename_snapshot("work", "new", force=False)

    assert old_path.exists()
    assert old_path.read_text() == original_snapshot
    assert not new_path.exists()


def test_rename_snapshot_force_over_existing_target_restores_both_files_on_registry_failure(
    tmp_path, monkeypatch
) -> None:
    store = AccountStore(tmp_path)
    source_snapshot = make_snapshot("acct-source")
    target_snapshot = make_snapshot("acct-target")
    store.save_snapshot("work", source_snapshot, force=False, mark_active=True)
    store.save_snapshot("new", target_snapshot, force=False, mark_active=False)

    old_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    new_path = tmp_path / ".codex-account-switcher" / "accounts" / "new.json"
    original_source_text = old_path.read_text()
    original_target_text = new_path.read_text()

    def fail_registry_write(path, payload):  # type: ignore[no-untyped-def]
        if path == store.registry_path:
            raise OSError("registry write failed")
        store._write_json_original(path, payload)

    store._write_json_original = store._write_json_atomic  # type: ignore[attr-defined]
    monkeypatch.setattr(store, "_write_json_atomic", fail_registry_write)

    with pytest.raises(OSError, match="registry write failed"):
        store.rename_snapshot("work", "new", force=True)

    assert old_path.read_text() == original_source_text
    assert new_path.read_text() == original_target_text


def test_load_snapshots_returns_saved_metadata_and_snapshots(tmp_path) -> None:
    store = AccountStore(tmp_path)
    source_raw = make_snapshot("acct-work")
    store.save_snapshot("work", source_raw, force=False, mark_active=True)

    snapshots = store.load_snapshots(["work"])

    assert len(snapshots) == 1
    metadata, snapshot = snapshots[0]
    assert metadata.name == "work"
    assert metadata.account_id == "acct-work"
    assert snapshot.raw == source_raw


def test_save_snapshot_creates_codex_dir(tmp_path) -> None:
    store = AccountStore(tmp_path)

    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=False)

    assert store.codex_dir.exists()
    assert (store.codex_dir / "auth.json").exists() is False


def test_import_snapshots_rejects_duplicate_target_names(tmp_path) -> None:
    store = AccountStore(tmp_path)
    work_account = TransferAccount(
        name="work",
        metadata=build_metadata("work", parse_snapshot(make_snapshot("acct-work"))),
        snapshot=parse_snapshot(make_snapshot("acct-work")),
    )
    personal_account = TransferAccount(
        name="personal",
        metadata=build_metadata("personal", parse_snapshot(make_snapshot("acct-personal"))),
        snapshot=parse_snapshot(make_snapshot("acct-personal")),
    )
    plan = [
        ImportPlanItem(source_name="work", target_name="shared", action="rename"),
        ImportPlanItem(source_name="personal", target_name="shared", action="rename"),
    ]

    with pytest.raises(ValueError, match="Duplicate import target name: shared"):
        store.import_snapshots([work_account, personal_account], plan)

    assert not store.accounts_dir.exists()
    assert not store.registry_path.exists()


def test_import_snapshots_rejects_invalid_later_plan_item_before_any_writes(tmp_path) -> None:
    store = AccountStore(tmp_path)
    work_account = TransferAccount(
        name="work",
        metadata=build_metadata("work", parse_snapshot(make_snapshot("acct-work"))),
        snapshot=parse_snapshot(make_snapshot("acct-work")),
    )
    personal_account = TransferAccount(
        name="personal",
        metadata=build_metadata("personal", parse_snapshot(make_snapshot("acct-personal"))),
        snapshot=parse_snapshot(make_snapshot("acct-personal")),
    )
    plan = [
        ImportPlanItem(source_name="work", target_name="work-copy", action="rename"),
        ImportPlanItem(source_name="personal", target_name="bad name", action="rename"),
    ]

    with pytest.raises(ValueError, match="Invalid account name"):
        store.import_snapshots([work_account, personal_account], plan)

    assert not store.accounts_dir.exists()
    assert not store.registry_path.exists()

def test_import_snapshots_rejects_invalid_action_without_writes(tmp_path) -> None:
    store = AccountStore(tmp_path)
    imported_account = TransferAccount(
        name="travel",
        metadata=build_metadata("travel", parse_snapshot(make_snapshot("acct-travel"))),
        snapshot=parse_snapshot(make_snapshot("acct-travel")),
    )
    plan = [
        ImportPlanItem(source_name="travel", target_name="travel", action="archive"),
    ]

    with pytest.raises(ValueError, match="Invalid import action: archive"):
        store.import_snapshots([imported_account], plan)

    assert not store.accounts_dir.exists()
    assert not store.registry_path.exists()


def test_import_snapshots_preserves_archive_metadata_on_import(tmp_path) -> None:
    store = AccountStore(tmp_path)
    imported_account = TransferAccount(
        name="travel",
        metadata=build_metadata("travel", parse_snapshot(make_snapshot("acct-travel"))),
        snapshot=parse_snapshot(make_snapshot("acct-travel")),
    )
    imported_account.metadata.created_at = "2020-01-01T00:00:00Z"
    imported_account.metadata.updated_at = "2020-02-02T00:00:00Z"
    imported_account.metadata.last_verified_at = "2020-03-03T00:00:00Z"
    plan = [
        ImportPlanItem(source_name="travel", target_name="vacation", action="rename"),
    ]

    result = store.import_snapshots([imported_account], plan)

    assert result.imported == ["vacation"]
    registry = store.load_registry()
    assert registry["accounts"]["vacation"]["name"] == "vacation"
    assert registry["accounts"]["vacation"]["created_at"] == "2020-01-01T00:00:00Z"
    assert registry["accounts"]["vacation"]["updated_at"] == "2020-02-02T00:00:00Z"
    assert registry["accounts"]["vacation"]["last_verified_at"] == "2020-03-03T00:00:00Z"


def test_import_snapshots_rejects_duplicate_archive_names_before_writes(tmp_path) -> None:
    store = AccountStore(tmp_path)
    first_work_account = TransferAccount(
        name="work",
        metadata=build_metadata("work", parse_snapshot(make_snapshot("acct-first-work"))),
        snapshot=parse_snapshot(make_snapshot("acct-first-work")),
    )
    second_work_account = TransferAccount(
        name="work",
        metadata=build_metadata("work", parse_snapshot(make_snapshot("acct-second-work"))),
        snapshot=parse_snapshot(make_snapshot("acct-second-work")),
    )
    plan = [
        ImportPlanItem(source_name="work", target_name="work-copy", action="rename"),
    ]

    with pytest.raises(ValueError, match="Duplicate import source account name: work"):
        store.import_snapshots([first_work_account, second_work_account], plan)

    assert not store.accounts_dir.exists()
    assert not store.registry_path.exists()


def test_import_snapshots_does_not_create_codex_dir(tmp_path) -> None:
    store = AccountStore(tmp_path)
    imported_account = TransferAccount(
        name="travel",
        metadata=build_metadata("travel", parse_snapshot(make_snapshot("acct-travel"))),
        snapshot=parse_snapshot(make_snapshot("acct-travel")),
    )
    plan = [
        ImportPlanItem(source_name="travel", target_name="travel", action="import"),
    ]

    result = store.import_snapshots([imported_account], plan)

    assert result.imported == ["travel"]
    assert not store.codex_dir.exists()
    assert (store.accounts_dir / "travel.json").exists()
    assert store.registry_path.exists()
