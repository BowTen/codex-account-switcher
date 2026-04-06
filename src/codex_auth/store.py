from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from .models import AccountMetadata, AccountSnapshot, ImportPlanItem, ImportResult, TransferAccount
from .validators import build_metadata, parse_snapshot, validate_account_name


class AccountStore:
    def __init__(self, home: Path | str | None = None) -> None:
        self.home = Path(home).expanduser() if home is not None else Path.home()
        self.codex_dir = self.home / ".codex"
        self.root = self.home / ".codex-account-switcher"
        self.accounts_dir = self.root / "accounts"
        self.registry_path = self.root / "registry.json"
        self.live_auth_path = self.codex_dir / "auth.json"

    def ensure_store_dirs(self) -> None:
        self.accounts_dir.mkdir(parents=True, exist_ok=True)

    def ensure_codex_dirs(self) -> None:
        self.codex_dir.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "active_name": None, "accounts": {}}
        return json.loads(self.registry_path.read_text())

    def save_registry(self, registry: dict[str, Any]) -> None:
        self.ensure_store_dirs()
        self._write_json_atomic(self.registry_path, registry)

    def load_snapshot(self, name: str) -> AccountSnapshot:
        validate_account_name(name)
        path = self.accounts_dir / f"{name}.json"
        if not path.exists():
            raise ValueError(f"Unknown account: {name}")
        return parse_snapshot(json.loads(path.read_text()))

    def load_snapshots(self, names: list[str]) -> list[tuple[AccountMetadata, AccountSnapshot]]:
        snapshots: list[tuple[AccountMetadata, AccountSnapshot]] = []
        registry = self.load_registry()
        for name in names:
            validate_account_name(name)
            entry = registry["accounts"].get(name)
            if entry is None:
                raise ValueError(f"Unknown account: {name}")
            snapshots.append((AccountMetadata(**entry), self.load_snapshot(name)))
        return snapshots

    def save_snapshot(
        self,
        name: str,
        raw: dict[str, Any],
        *,
        force: bool,
        mark_active: bool,
        ensure_codex_dir: bool = True,
    ) -> AccountMetadata:
        name = validate_account_name(name)
        self.ensure_store_dirs()
        if ensure_codex_dir:
            self.ensure_codex_dirs()
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

        previous_snapshot = path.read_bytes() if path.exists() else None
        self._write_json_atomic(path, raw)
        registry["accounts"][name] = metadata.to_dict()
        if mark_active:
            registry["active_name"] = name
        try:
            self.save_registry(registry)
        except Exception:
            if previous_snapshot is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(previous_snapshot)
                os.chmod(path, 0o600)
            raise
        return metadata

    def import_snapshots(
        self,
        accounts: list[TransferAccount],
        plan: list[ImportPlanItem],
    ) -> ImportResult:
        if not plan:
            return ImportResult(imported=[], overwritten=[], renamed=[], skipped=[])

        account_by_name: dict[str, TransferAccount] = {}
        for account in accounts:
            if account.name in account_by_name:
                raise ValueError(f"Duplicate import source account name: {account.name}")
            account_by_name[account.name] = account

        registry = self.load_registry()
        imported: list[str] = []
        overwritten: list[str] = []
        renamed: list[str] = []
        skipped: list[str] = []
        prepared_plan: list[tuple[TransferAccount, str, bool]] = []
        seen_targets: set[str] = set()

        for item in plan:
            source_account = account_by_name.get(item.source_name)
            if source_account is None:
                raise ValueError(f"Unknown import source account: {item.source_name}")
            try:
                self._validate_import_source_account(source_account)
            except ValueError:
                raise ValueError(f"Invalid import source account: {item.source_name}") from None
            if item.action == "skip":
                skipped.append(item.source_name)
                continue
            if item.action not in {"import", "rename", "overwrite"}:
                raise ValueError(f"Invalid import action: {item.action}")
            target_name = validate_account_name(item.target_name)
            if target_name in seen_targets:
                raise ValueError(f"Duplicate import target name: {target_name}")
            if target_name in registry["accounts"] and item.action != "overwrite":
                raise ValueError(f"Account already exists: {target_name}")
            if target_name not in registry["accounts"] and item.action == "overwrite":
                raise ValueError(f"Cannot overwrite missing account: {target_name}")
            seen_targets.add(target_name)
            prepared_plan.append((source_account, target_name, item.action == "overwrite"))

        self.ensure_store_dirs()
        updated_registry = deepcopy(registry)
        path_backups: dict[Path, bytes | None] = {}

        try:
            for source_account, target_name, force in prepared_plan:
                path = self.accounts_dir / f"{target_name}.json"
                if path not in path_backups:
                    path_backups[path] = path.read_bytes() if path.exists() else None

                self._write_json_atomic(path, source_account.snapshot.raw)

                metadata_dict = dict(source_account.metadata.to_dict())
                metadata_dict["name"] = target_name
                updated_registry["accounts"][target_name] = metadata_dict

                imported.append(target_name)
                if force:
                    overwritten.append(target_name)
                if target_name != source_account.name:
                    renamed.append(target_name)

            self.save_registry(updated_registry)
        except Exception:
            for path, previous_bytes in path_backups.items():
                if previous_bytes is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_bytes(previous_bytes)
                    os.chmod(path, 0o600)
            raise

        return ImportResult(
            imported=imported,
            overwritten=overwritten,
            renamed=renamed,
            skipped=skipped,
        )

    def _validate_import_source_account(self, account: TransferAccount) -> None:
        parsed_snapshot = parse_snapshot(account.snapshot.raw)
        validate_account_name(account.name)
        validate_account_name(account.metadata.name)
        if account.metadata.name != account.name:
            raise ValueError("metadata name mismatch")
        if account.metadata.auth_mode != parsed_snapshot.auth_mode:
            raise ValueError("metadata auth mode mismatch")
        if account.metadata.account_id != parsed_snapshot.account_id:
            raise ValueError("metadata account id mismatch")
        if account.metadata.last_refresh != parsed_snapshot.last_refresh:
            raise ValueError("metadata last refresh mismatch")
        if account.snapshot.auth_mode != parsed_snapshot.auth_mode:
            raise ValueError("snapshot auth mode mismatch")
        if account.snapshot.account_id != parsed_snapshot.account_id:
            raise ValueError("snapshot account id mismatch")
        if account.snapshot.last_refresh != parsed_snapshot.last_refresh:
            raise ValueError("snapshot last refresh mismatch")

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

        try:
            live = self.read_live_auth()
            if live is None:
                return None

            live_snapshot = parse_snapshot(live)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
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
        backup = path.read_bytes() if path.exists() else None
        if path.exists():
            path.unlink()
        registry["accounts"].pop(name)
        if registry["active_name"] == name:
            registry["active_name"] = None
        try:
            self.save_registry(registry)
        except Exception:
            if backup is not None:
                path.write_bytes(backup)
                os.chmod(path, 0o600)
            raise

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
        old_snapshot = old_path.read_bytes()
        new_snapshot = new_path.read_bytes() if new_path.exists() else None
        self.ensure_store_dirs()
        old_path.replace(new_path)

        entry = registry["accounts"].pop(old)
        entry["name"] = new
        registry["accounts"][new] = entry
        if registry["active_name"] == old:
            registry["active_name"] = new
        try:
            self.save_registry(registry)
        except Exception:
            old_path.write_bytes(old_snapshot)
            os.chmod(old_path, 0o600)
            if new_snapshot is None:
                if new_path.exists():
                    new_path.unlink()
            else:
                new_path.write_bytes(new_snapshot)
                os.chmod(new_path, 0o600)
            raise

    def read_live_auth(self) -> dict[str, Any] | None:
        if not self.live_auth_path.exists():
            return None
        return json.loads(self.live_auth_path.read_text())

    def write_live_auth(self, raw: dict[str, Any]) -> None:
        self.ensure_codex_dirs()
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
