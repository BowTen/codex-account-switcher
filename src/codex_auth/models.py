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
    format_version: int
    kdf: str
    kdf_params: dict[str, Any]
    cipher: str
    nonce: bytes
    ciphertext: bytes
    accounts: list[TransferAccount]
    exported_at: str | None = None
    tool_version: str | None = None


@dataclass(slots=True)
class ImportPlanItem:
    source_account: TransferAccount
    target_name: str
    action: str


@dataclass(slots=True)
class ImportResult:
    imported: list[str]
    overwritten: list[str]
    renamed: list[str]
    skipped: list[str]
