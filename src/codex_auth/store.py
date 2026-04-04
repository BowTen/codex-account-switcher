from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import AccountMetadata, AccountSnapshot
from .validators import build_metadata, parse_snapshot, validate_account_name


class AccountStore:
    def __init__(self, home: Path | str | None = None) -> None:
        self.home = Path(home).expanduser() if home is not None else Path.home()
        self.codex_dir = self.home / ".codex"
        self.root = self.home / ".codex-account-switcher"
        self.accounts_dir = self.root / "accounts"
        self.registry_path = self.root / "registry.json"
        self.live_auth_path = self.codex_dir / "auth.json"

    def ensure_dirs(self) -> None:
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self.codex_dir.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "active_name": None, "accounts": {}}
        return json.loads(self.registry_path.read_text())

    def save_registry(self, registry: dict[str, Any]) -> None:
        self.ensure_dirs()
        self._write_json_atomic(self.registry_path, registry)

    def load_snapshot(self, name: str) -> AccountSnapshot:
        validate_account_name(name)
        path = self.accounts_dir / f"{name}.json"
        if not path.exists():
            raise ValueError(f"Unknown account: {name}")
        return parse_snapshot(json.loads(path.read_text()))

    def save_snapshot(
        self,
        name: str,
        raw: dict[str, Any],
        *,
        force: bool,
        mark_active: bool,
    ) -> AccountMetadata:
        name = validate_account_name(name)
        self.ensure_dirs()
        path = self.accounts_dir / f"{name}.json"
        if path.exists() and not force:
            raise ValueError(f"Account already exists: {name}")

        snapshot = parse_snapshot(raw)
        registry = self.load_registry()
        existing = registry["accounts"].get(name)
        created_at = existing["created_at"] if existing else None
        last_verified_at = existing["last_verified_at"] if existing else None
        metadata = build_metadata(
            name,
            snapshot,
            created_at=created_at,
            last_verified_at=last_verified_at,
        )

        self._write_json_atomic(path, raw)
        registry["accounts"][name] = metadata.to_dict()
        if mark_active:
            registry["active_name"] = name
        self.save_registry(registry)
        return metadata

    def list_metadata(self) -> list[AccountMetadata]:
        registry = self.load_registry()
        accounts = registry["accounts"].values()
        return [AccountMetadata(**item) for item in sorted(accounts, key=lambda item: item["name"])]

    def current_active_name(self) -> str | None:
        return self.load_registry()["active_name"]

    def matched_active_name(self) -> str | None:
        active_name = self.current_active_name()
        if not active_name:
            return None

        live = self.read_live_auth()
        if live is None:
            return None

        live_snapshot = parse_snapshot(live)
        registry = self.load_registry()
        entry = registry["accounts"].get(active_name)
        if entry is None:
            return None

        if entry["auth_mode"] != live_snapshot.auth_mode:
            return None
        if entry["account_id"] != live_snapshot.account_id:
            return None
        return active_name

    def remove_snapshot(self, name: str, *, force_current: bool) -> None:
        registry = self.load_registry()
        if name not in registry["accounts"]:
            raise ValueError(f"Unknown account: {name}")
        if registry["active_name"] == name and not force_current:
            raise ValueError("Refusing to remove the currently active account without --force-current")

        path = self.accounts_dir / f"{name}.json"
        if path.exists():
            path.unlink()
        registry["accounts"].pop(name)
        if registry["active_name"] == name:
            registry["active_name"] = None
        self.save_registry(registry)

    def rename_snapshot(self, old: str, new: str, *, force: bool) -> None:
        old = validate_account_name(old)
        new = validate_account_name(new)
        registry = self.load_registry()
        if old not in registry["accounts"]:
            raise ValueError(f"Unknown account: {old}")
        if new in registry["accounts"] and not force:
            raise ValueError(f"Account already exists: {new}")

        old_path = self.accounts_dir / f"{old}.json"
        new_path = self.accounts_dir / f"{new}.json"
        self.ensure_dirs()
        old_path.replace(new_path)

        entry = registry["accounts"].pop(old)
        entry["name"] = new
        registry["accounts"][new] = entry
        if registry["active_name"] == old:
            registry["active_name"] = new
        self.save_registry(registry)

    def read_live_auth(self) -> dict[str, Any] | None:
        if not self.live_auth_path.exists():
            return None
        return json.loads(self.live_auth_path.read_text())

    def write_live_auth(self, raw: dict[str, Any]) -> None:
        self.ensure_dirs()
        self._write_json_atomic(self.live_auth_path, raw)

    def mark_verified(self, name: str, verified_at: str) -> None:
        registry = self.load_registry()
        entry = registry["accounts"][name]
        entry["last_verified_at"] = verified_at
        registry["active_name"] = name
        self.save_registry(registry)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)
