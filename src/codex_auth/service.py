from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping

from .codex_cli import run_login_status
from .models import AccountMetadata, UseResult
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
        try:
            self.store.load_registry()
        except Exception:
            registry_valid = "false"
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
            "live_auth_exists": str(self.store.live_auth_path.exists()).lower(),
            "live_auth_valid": live_auth_valid,
            "store_root": str(self.store.root),
            "registry_exists": str(self.store.registry_path.exists()).lower(),
            "registry_valid": registry_valid,
        }
