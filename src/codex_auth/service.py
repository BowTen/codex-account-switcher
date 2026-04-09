from __future__ import annotations

import json
import os
import queue
import shutil
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping

from . import __version__
from .codex_cli import run_login_status
from .errors import UsageTimeoutError
from .models import (
    AccountMetadata,
    AccountUsageResult,
    ImportPlanItem,
    ImportResult,
    TransferAccount,
    TransferArchive,
    UsageBatchAbortedEvent,
    UsageBatchCompletedEvent,
    UsageBatchEvent,
    UsageBatchPhaseEvent,
    UsageBatchQueuedEvent,
    UsageBatchRunningEvent,
    UsageQueryTarget,
    UseResult,
)
from .store import AccountStore
from .token_refresh import access_token_needs_refresh, refresh_chatgpt_credentials
from .usage_api import fetch_usage, probe_usage_endpoint
from .transfer import decrypt_transfer_archive, encrypt_transfer_archive
from .validators import parse_snapshot, utc_now_iso, validate_account_name

LIVE_USAGE_DISPLAY_NAME = "(live)"
USAGE_BATCH_MAX_WORKERS = 4


@dataclass(slots=True)
class _UsageTimeoutContext:
    account_id: str
    refreshed_raw: dict[str, object] | None


class _UsageFetchTimeout(UsageTimeoutError):
    def __init__(self, message: str, *, context: _UsageTimeoutContext) -> None:
        super().__init__(message)
        self.context = context


@dataclass(slots=True)
class _UsageBatchWorkItem:
    index: int
    target: UsageQueryTarget


@dataclass(slots=True)
class _UsageBatchResult:
    index: int
    target: UsageQueryTarget
    result: AccountUsageResult | None = None
    timeout: UsageTimeoutError | None = None


def fetch_account_usage_snapshot(target: UsageQueryTarget) -> AccountUsageResult:
    snapshot = parse_snapshot(target.raw)
    raw = snapshot.raw
    tokens = raw["tokens"]

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    id_token = tokens["id_token"]
    account_id = snapshot.account_id
    refreshed = False
    refreshed_raw: dict[str, object] | None = None

    if access_token_needs_refresh(access_token):
        refreshed_tokens = refresh_chatgpt_credentials(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            account_id=account_id,
        )
        refreshed = True
        account_id = refreshed_tokens.account_id or account_id
        access_token = refreshed_tokens.access_token
        refreshed_raw = dict(raw)
        refreshed_raw["tokens"] = {
            **tokens,
            "access_token": refreshed_tokens.access_token,
            "refresh_token": refreshed_tokens.refresh_token,
            "id_token": refreshed_tokens.id_token,
            "account_id": account_id,
        }
        refreshed_raw["last_refresh"] = refreshed_tokens.expires_at or utc_now_iso()

    try:
        usage = fetch_usage(access_token=access_token, account_id=account_id)
    except UsageTimeoutError as exc:
        raise _UsageFetchTimeout(
            str(exc),
            context=_UsageTimeoutContext(account_id=account_id, refreshed_raw=refreshed_raw),
        ) from None
    except Exception as exc:  # noqa: BLE001
        return AccountUsageResult(
            name=target.name,
            managed_state=target.managed_state,
            account_id=account_id,
            plan_type=None,
            primary_window=None,
            secondary_window=None,
            credits_balance=None,
            has_credits=None,
            unlimited_credits=None,
            refreshed=refreshed,
            refreshed_raw=refreshed_raw,
            error=str(exc),
        )
    credits_balance: str | None = None
    has_credits: bool | None = None
    unlimited_credits: bool | None = None
    if usage.credits is not None:
        credits_balance = None if usage.credits.balance is None else str(usage.credits.balance)
        has_credits = usage.credits.has_credits
        unlimited_credits = usage.credits.unlimited

    return AccountUsageResult(
        name=target.name,
        managed_state=target.managed_state,
        account_id=account_id,
        plan_type=usage.plan_type,
        primary_window=usage.primary_window,
        secondary_window=usage.secondary_window,
        credits_balance=credits_balance,
        has_credits=has_credits,
        unlimited_credits=unlimited_credits,
        refreshed=refreshed,
        refreshed_raw=refreshed_raw,
        error=None,
    )


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

    def get_usage_account(self, name: str) -> AccountUsageResult:
        probe_usage_endpoint()
        target = self._build_managed_usage_target(name)
        try:
            result = self._fetch_usage_target(target)
        except UsageTimeoutError as exc:
            self._persist_usage_refresh(target, self._usage_timeout_result(target, exc))
            raise
        self._persist_usage_refresh(target, result)
        return result

    def stream_usage_accounts(self) -> Iterator[UsageBatchEvent]:
        targets = self._list_usage_targets()
        queued_names = [target.name for target in targets]
        running_names: list[str] = []

        yield UsageBatchPhaseEvent(
            phase="prechecking network",
            queued_names=list(queued_names),
            running_names=list(running_names),
        )
        try:
            probe_usage_endpoint()
        except UsageTimeoutError as exc:
            yield UsageBatchAbortedEvent(
                phase="aborted (timeout)",
                queued_names=list(queued_names),
                running_names=list(running_names),
                error=str(exc),
                timed_out_name=None,
            )
            return
        yield UsageBatchPhaseEvent(
            phase="querying",
            queued_names=list(queued_names),
            running_names=list(running_names),
        )

        worker_count = min(USAGE_BATCH_MAX_WORKERS, len(targets))
        if worker_count == 0:
            yield UsageBatchPhaseEvent(
                phase="completed",
                queued_names=[],
                running_names=[],
            )
            return

        work_queue: queue.Queue[_UsageBatchWorkItem | None] = queue.Queue()
        result_queue: queue.Queue[_UsageBatchResult] = queue.Queue()
        stop_event = threading.Event()

        def worker() -> None:
            while True:
                item = work_queue.get()
                if item is None:
                    return
                if stop_event.is_set():
                    continue
                try:
                    result = self._fetch_usage_target(item.target)
                except UsageTimeoutError as exc:
                    stop_event.set()
                    result_queue.put(_UsageBatchResult(index=item.index, target=item.target, timeout=exc))
                    return
                except Exception as exc:  # noqa: BLE001
                    result = self._usage_fetch_error_result(item.target, exc)
                result_queue.put(_UsageBatchResult(index=item.index, target=item.target, result=result))

        for worker_index in range(worker_count):
            thread = threading.Thread(
                target=worker,
                name=f"usage-stream-worker-{worker_index}",
                daemon=True,
            )
            thread.start()

        next_index_to_start = 0

        def start_next_target() -> bool:
            nonlocal next_index_to_start
            if next_index_to_start >= len(targets):
                return False
            item = _UsageBatchWorkItem(index=next_index_to_start, target=targets[next_index_to_start])
            next_index_to_start += 1
            work_queue.put(item)
            running_names.append(item.target.name)
            queued_names.remove(item.target.name)
            return True

        for _ in range(worker_count):
            if not start_next_target():
                break
            yield UsageBatchRunningEvent(
                phase="querying",
                queued_names=list(queued_names),
                running_names=list(running_names),
            )
            yield UsageBatchQueuedEvent(
                phase="querying",
                queued_names=list(queued_names),
                running_names=list(running_names),
            )

        processed = 0
        try:
            while processed < len(targets):
                item = result_queue.get()
                if item.target.name in running_names:
                    running_names.remove(item.target.name)
                if item.timeout is not None:
                    timeout_result = self._usage_timeout_result(item.target, item.timeout)
                    self._persist_usage_refresh(item.target, timeout_result)
                    stop_event.set()
                    yield UsageBatchAbortedEvent(
                        phase="aborted (timeout)",
                        queued_names=list(queued_names),
                        running_names=list(running_names),
                        error=str(item.timeout),
                        timed_out_name=item.target.name,
                    )
                    return
                assert item.result is not None
                processed += 1
                self._persist_usage_refresh(item.target, item.result)
                yield UsageBatchCompletedEvent(
                    phase="querying",
                    queued_names=list(queued_names),
                    running_names=list(running_names),
                    result=item.result,
                )
                if start_next_target():
                    yield UsageBatchRunningEvent(
                        phase="querying",
                        queued_names=list(queued_names),
                        running_names=list(running_names),
                    )
                    yield UsageBatchQueuedEvent(
                        phase="querying",
                        queued_names=list(queued_names),
                        running_names=list(running_names),
                    )
        finally:
            stop_event.set()
            for _ in range(worker_count):
                work_queue.put(None)

        yield UsageBatchPhaseEvent(
            phase="completed",
            queued_names=list(queued_names),
            running_names=list(running_names),
        )

    def list_usage_accounts(self) -> list[AccountUsageResult]:
        probe_usage_endpoint()
        targets = self._list_usage_targets()
        results: list[AccountUsageResult | None] = [None] * len(targets)
        completed: dict[int, tuple[UsageQueryTarget, AccountUsageResult]] = {}
        next_flush_index = 0
        worker_count = min(USAGE_BATCH_MAX_WORKERS, len(targets))
        if worker_count == 0:
            return []

        work_queue: queue.Queue[_UsageBatchWorkItem | None] = queue.Queue()
        result_queue: queue.Queue[_UsageBatchResult] = queue.Queue()
        stop_event = threading.Event()

        for index, target in enumerate(targets):
            work_queue.put(_UsageBatchWorkItem(index=index, target=target))
        for _ in range(worker_count):
            work_queue.put(None)

        def worker() -> None:
            while True:
                item = work_queue.get()
                if item is None:
                    return
                if stop_event.is_set():
                    continue
                try:
                    result = self._fetch_usage_target(item.target)
                except UsageTimeoutError as exc:
                    stop_event.set()
                    result_queue.put(_UsageBatchResult(index=item.index, target=item.target, timeout=exc))
                    return
                except Exception as exc:  # noqa: BLE001
                    result = self._usage_fetch_error_result(item.target, exc)
                result_queue.put(_UsageBatchResult(index=item.index, target=item.target, result=result))

        for worker_index in range(worker_count):
            thread = threading.Thread(
                target=worker,
                name=f"usage-batch-worker-{worker_index}",
                daemon=True,
            )
            thread.start()

        processed = 0
        while processed < len(targets):
            item = result_queue.get()
            if item.timeout is not None:
                self._persist_usage_refresh(item.target, self._usage_timeout_result(item.target, item.timeout))
                raise item.timeout
            assert item.result is not None
            processed += 1
            completed[item.index] = (item.target, item.result)
            while next_flush_index in completed:
                flush_target, flush_result = completed.pop(next_flush_index)
                self._persist_usage_refresh(flush_target, flush_result)
                results[next_flush_index] = flush_result
                next_flush_index += 1
        if any(result is None for result in results):
            raise RuntimeError("usage result collection failed")
        return [result for result in results if result is not None]

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
            accounts=accounts,
            exported_at=utc_now_iso(),
            tool_version=__version__,
        )

    def apply_import_archive(
        self,
        archive: TransferArchive,
        plan: list[ImportPlanItem],
    ) -> ImportResult:
        return self.store.import_snapshots(archive.accounts, plan)

    def write_export_archive(self, names: list[str], path: Path | str, *, passphrase: str) -> None:
        archive = self.build_export_archive(names)
        blob = encrypt_transfer_archive(
            archive.accounts,
            passphrase=passphrase,
            exported_at=archive.exported_at,
            tool_version=archive.tool_version,
        )
        archive_path = Path(path)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = archive_path.with_name(f"{archive_path.name}.tmp.{os.getpid()}")
        try:
            tmp_path.write_bytes(blob)
            os.chmod(tmp_path, 0o600)
            tmp_path.replace(archive_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def read_import_archive(self, path: Path | str, *, passphrase: str) -> TransferArchive:
        return decrypt_transfer_archive(Path(path).read_bytes(), passphrase=passphrase)

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

    def _build_managed_usage_target(self, name: str) -> UsageQueryTarget:
        name = validate_account_name(name)
        if name not in self.store.load_registry()["accounts"]:
            raise ValueError(f"Unknown account: {name}")
        snapshot = self.store.load_snapshot(name)
        return UsageQueryTarget(
            name=name,
            managed_state="managed",
            account_id=snapshot.account_id,
            raw=snapshot.raw,
            managed_name=name,
        )

    def _build_live_usage_target(self) -> UsageQueryTarget | None:
        raw = self.store.read_live_auth()
        if raw is None:
            return None
        try:
            snapshot = parse_snapshot(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

        registry = self.store.load_registry()
        for entry in registry.get("accounts", {}).values():
            if entry.get("auth_mode") == snapshot.auth_mode and entry.get("account_id") == snapshot.account_id:
                return None

        return UsageQueryTarget(
            name=LIVE_USAGE_DISPLAY_NAME,
            managed_state="unmanaged",
            account_id=snapshot.account_id,
            raw=raw,
            managed_name=None,
        )

    def _list_usage_targets(self) -> list[UsageQueryTarget]:
        targets: list[UsageQueryTarget] = []
        live_target = self._build_live_usage_target()
        if live_target is not None:
            targets.append(live_target)

        for metadata in self.store.list_metadata():
            try:
                snapshot = self.store.load_snapshot(metadata.name)
                raw = snapshot.raw
                account_id = snapshot.account_id
            except Exception:
                raw = {}
                account_id = metadata.account_id
            targets.append(
                UsageQueryTarget(
                    name=metadata.name,
                    managed_state="managed",
                    account_id=account_id,
                    raw=raw,
                    managed_name=metadata.name,
                )
            )
        return targets

    def _fetch_usage_target(self, target: UsageQueryTarget) -> AccountUsageResult:
        try:
            result = fetch_account_usage_snapshot(target)
        except UsageTimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001
            return self._usage_fetch_error_result(target, exc)
        if result.error is None:
            return result
        return result

    def _usage_fetch_error_result(self, target: UsageQueryTarget, exc: Exception) -> AccountUsageResult:
        return AccountUsageResult(
            name=target.name,
            managed_state=target.managed_state,
            account_id=target.account_id,
            plan_type=None,
            primary_window=None,
            secondary_window=None,
            credits_balance=None,
            has_credits=None,
            unlimited_credits=None,
            refreshed=False,
            refreshed_raw=None,
            error=str(exc),
        )

    def _usage_timeout_result(self, target: UsageQueryTarget, exc: UsageTimeoutError) -> AccountUsageResult:
        if isinstance(exc, _UsageFetchTimeout):
            account_id = exc.context.account_id
            refreshed_raw = exc.context.refreshed_raw
        else:
            account_id = target.account_id
            refreshed_raw = None
        return AccountUsageResult(
            name=target.name,
            managed_state=target.managed_state,
            account_id=account_id,
            plan_type=None,
            primary_window=None,
            secondary_window=None,
            credits_balance=None,
            has_credits=None,
            unlimited_credits=None,
            refreshed=refreshed_raw is not None,
            refreshed_raw=refreshed_raw,
            error=str(exc),
        )

    def _persist_usage_refresh(self, target: UsageQueryTarget, result: AccountUsageResult) -> None:
        if not result.refreshed or result.refreshed_raw is None:
            return
        if target.managed_name is not None:
            self.store.overwrite_snapshot(target.managed_name, result.refreshed_raw)
        if self.store.live_matches_snapshot(target.raw):
            self.store.write_live_auth(result.refreshed_raw)
