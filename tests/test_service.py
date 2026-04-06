import os
import stat
from pathlib import Path

import pytest

from codex_auth import __version__
from codex_auth.models import AccountMetadata, ImportPlanItem, TransferAccount, TransferArchive
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
