from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Mapping

from .codex_cli import run_login_status
from .models import AccountMetadata, ImportPlanItem, ImportResult, TransferAccount, TransferArchive, UseResult
from .store import AccountStore
from .validators import parse_snapshot, utc_now_iso, validate_account_name


class CodexAuthService:
    def __init__(
        self,
        *,
        home: Path | str | None = None,
        codex_executable: str = "codex",
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.store = AccountStore(home)
        self.codex_executable = codex_executable
        self.env = env

    def save_current(self, name: str, *, force: bool) -> AccountMetadata:
        validate_account_name(name)
        raw = self.store.read_live_auth()
        if raw is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        return self.store.save_snapshot(name, raw, force=force, mark_active=True)

    def use_account(self, name: str) -> UseResult:
        validate_account_name(name)
        current_name = self.store.matched_active_name()
        current_live = self.store.read_live_auth()
        if current_name and current_live is not None:
            self.store.save_snapshot(current_name, current_live, force=True, mark_active=True)

        target = self.store.load_snapshot(name)
        self.store.write_live_auth(target.raw)
        registry = self.store.load_registry()
        registry["active_name"] = name
        self.store.save_registry(registry)

        verification = run_login_status(self.codex_executable, env=self.env)
        if verification.ok:
            self.store.mark_verified(name, utc_now_iso())

        return UseResult(
            switched=True,
            verified=verification.ok,
            account_name=name,
            verification=verification,
        )

    def list_accounts(self) -> list[AccountMetadata]:
        return self.store.list_metadata()

    def build_export_archive(self, names: list[str]) -> TransferArchive:
        if not names:
            raise ValueError("No accounts selected for export")

        accounts: list[TransferAccount] = []
        for metadata, snapshot in self.store.load_snapshots(names):
            accounts.append(
                TransferAccount(
                    name=metadata.name,
                    metadata=metadata,
                    snapshot=snapshot,
                )
            )

        return TransferArchive(
            format_version=1,
            kdf="export",
            kdf_params={},
            cipher="none",
            nonce=b"",
            ciphertext=b"",
            accounts=accounts,
            exported_at=utc_now_iso(),
            tool_version="0.1.0",
        )

    def apply_import_archive(
        self,
        archive: TransferArchive,
        plan: list[ImportPlanItem],
    ) -> ImportResult:
        return self.store.import_snapshots(archive.accounts, plan)

    def active_account_name(self) -> str | None:
        return self.store.matched_active_name()

    def inspect_account(self, name: str) -> dict[str, str | None]:
        registry = self.store.load_registry()
        if name not in registry["accounts"]:
            raise ValueError(f"Unknown account: {name}")
        entry = registry["accounts"][name]
        return {
            "name": entry["name"],
            "managed_state": "managed",
            "auth_mode": entry["auth_mode"],
            "account_id": entry["account_id"],
            "created_at": entry["created_at"],
            "updated_at": entry["updated_at"],
            "last_refresh": entry["last_refresh"],
            "last_verified_at": entry["last_verified_at"],
        }

    def current_account(self) -> dict[str, str | None]:
        active_name = self.active_account_name()
        live = self.store.read_live_auth()
        if active_name:
            return self.inspect_account(active_name)
        if live is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        snapshot = parse_snapshot(live)
        return {
            "name": None,
            "managed_state": "unmanaged",
            "auth_mode": snapshot.auth_mode,
            "account_id": snapshot.account_id,
            "created_at": None,
            "updated_at": None,
            "last_refresh": snapshot.last_refresh,
            "last_verified_at": None,
        }

    def rename_account(self, old: str, new: str, *, force: bool) -> None:
        self.store.rename_snapshot(old, new, force=force)

    def remove_account(self, name: str, *, force_current: bool) -> None:
        self.store.remove_snapshot(name, force_current=force_current)

    def doctor(self) -> dict[str, str]:
        registry_valid = "true"
        live_auth_valid = "true"
        managed_snapshots_valid = "true"
        managed_snapshot_count = 0
        try:
            registry = self.store.load_registry()
        except Exception:
            registry_valid = "false"
            managed_snapshots_valid = "false"
            registry = {"accounts": {}}

        accounts = registry.get("accounts") if isinstance(registry, dict) else None
        if not isinstance(accounts, dict):
            registry_valid = "false"
            managed_snapshots_valid = "false"
            accounts = {}

        for name in accounts:
            snapshot_path = self.store.accounts_dir / f"{name}.json"
            try:
                parse_snapshot(json.loads(snapshot_path.read_text()))
                managed_snapshot_count += 1
            except Exception:
                managed_snapshots_valid = "false"

        try:
            live = self.store.read_live_auth()
            if live is not None:
                parse_snapshot(live)
        except Exception:
            live_auth_valid = "false"

        path_value = self.env.get("PATH") if self.env is not None else None
        return {
            "codex_on_path": str(shutil.which(self.codex_executable, path=path_value) is not None).lower(),
            "codex_dir": str(self.store.codex_dir),
            "codex_dir_exists": str(self.store.codex_dir.exists()).lower(),
            "codex_dir_creatable": str(self._path_creatable(self.store.codex_dir)).lower(),
            "live_auth_exists": str(self.store.live_auth_path.exists()).lower(),
            "live_auth_valid": live_auth_valid,
            "live_auth_mode_600": str(self._is_mode_600(self.store.live_auth_path)).lower(),
            "store_root": str(self.store.root),
            "store_root_exists": str(self.store.root.exists()).lower(),
            "store_root_creatable": str(self._path_creatable(self.store.root)).lower(),
            "registry_exists": str(self.store.registry_path.exists()).lower(),
            "registry_valid": registry_valid,
            "registry_mode_600": str(self._is_mode_600(self.store.registry_path)).lower(),
            "managed_snapshots_checked": str(managed_snapshot_count),
            "managed_snapshots_valid": managed_snapshots_valid,
        }

    def _path_creatable(self, path: Path) -> bool:
        target = path if path.exists() and path.is_dir() else path.parent
        return target.exists() and os.access(target, os.W_OK | os.X_OK)

    def _is_mode_600(self, path: Path) -> bool:
        try:
            return stat.S_IMODE(path.stat().st_mode) == 0o600
        except OSError:
            return False
