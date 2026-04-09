from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AccountSnapshot:
    auth_mode: str
    account_id: str
    last_refresh: str | None
    raw: dict[str, Any]


@dataclass(slots=True)
class AccountMetadata:
    name: str
    auth_mode: str
    account_id: str
    created_at: str
    updated_at: str
    last_refresh: str | None
    last_verified_at: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "auth_mode": self.auth_mode,
            "account_id": self.account_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_refresh": self.last_refresh,
            "last_verified_at": self.last_verified_at,
        }


@dataclass(slots=True)
class VerificationResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class UseResult:
    switched: bool
    verified: bool
    account_name: str
    verification: VerificationResult


@dataclass(slots=True)
class TransferAccount:
    name: str
    metadata: AccountMetadata
    snapshot: AccountSnapshot


@dataclass(slots=True)
class TransferArchive:
    accounts: list[TransferAccount]
    exported_at: str | None = None
    tool_version: str | None = None


@dataclass(slots=True)
class ImportPlanItem:
    source_name: str
    target_name: str
    action: str


@dataclass(slots=True)
class ImportResult:
    imported: list[str]
    overwritten: list[str]
    renamed: list[str]
    skipped: list[str]


@dataclass(slots=True)
class UsageWindow:
    used_percent: float | int | None
    limit_window_seconds: int | None
    reset_at: int | str | None
    raw: dict[str, Any] | None = None

    @property
    def remaining_percent(self) -> float | int | None:
        if self.used_percent is None:
            return None
        return max(0, 100 - self.used_percent)


@dataclass(slots=True)
class UsageCredits:
    has_credits: bool | None
    unlimited: bool | None
    balance: float | int | str | None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class UsageSnapshot:
    account_id: str
    plan_type: str | None
    primary_window: UsageWindow | None
    secondary_window: UsageWindow | None
    credits: UsageCredits | None = None
    raw: dict[str, Any] | None = None


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


@dataclass(slots=True)
class UsageBatchPhaseEvent:
    phase: str
    running_names: list[str]
    queued_names: list[str]


@dataclass(slots=True)
class UsageBatchRunningEvent:
    phase: str
    running_names: list[str]
    queued_names: list[str]


@dataclass(slots=True)
class UsageBatchQueuedEvent:
    phase: str
    running_names: list[str]
    queued_names: list[str]


@dataclass(slots=True)
class UsageBatchCompletedEvent:
    phase: str
    running_names: list[str]
    queued_names: list[str]
    result: AccountUsageResult


@dataclass(slots=True)
class UsageBatchAbortedEvent:
    phase: str
    running_names: list[str]
    queued_names: list[str]
    error: str
    timed_out_name: str | None
    timed_out: bool = True


UsageBatchEvent = (
    UsageBatchPhaseEvent
    | UsageBatchRunningEvent
    | UsageBatchQueuedEvent
    | UsageBatchCompletedEvent
    | UsageBatchAbortedEvent
)


@dataclass(slots=True)
class TokenRefreshResult:
    access_token: str
    refresh_token: str
    id_token: str
    account_id: str | None
    expires_in: int | None = None
    expires_at: str | None = None
    raw: dict[str, Any] | None = None
