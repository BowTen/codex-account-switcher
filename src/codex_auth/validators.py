from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .models import AccountMetadata, AccountSnapshot


NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def utc_now_iso() -> str:
    value = datetime.now(UTC).replace(microsecond=0).isoformat()
    return value.replace("+00:00", "Z")


def validate_account_name(name: str) -> str:
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid account name: {name!r}")
    return name


def parse_snapshot(raw: dict[str, Any]) -> AccountSnapshot:
    auth_mode = raw.get("auth_mode")
    tokens = raw.get("tokens")
    if not isinstance(auth_mode, str):
        raise ValueError("Missing or invalid auth_mode")
    if not isinstance(tokens, dict):
        raise ValueError("Missing or invalid tokens")

    required = ("access_token", "refresh_token", "id_token", "account_id")
    missing = [key for key in required if not isinstance(tokens.get(key), str)]
    if missing:
        raise ValueError(f"Missing required token fields: {', '.join(missing)}")

    return AccountSnapshot(
        auth_mode=auth_mode,
        account_id=tokens["account_id"],
        last_refresh=raw.get("last_refresh"),
        raw=raw,
    )


def build_metadata(
    name: str,
    snapshot: AccountSnapshot,
    *,
    created_at: str | None = None,
    last_verified_at: str | None = None,
) -> AccountMetadata:
    now = utc_now_iso()
    return AccountMetadata(
        name=validate_account_name(name),
        auth_mode=snapshot.auth_mode,
        account_id=snapshot.account_id,
        created_at=created_at or now,
        updated_at=now,
        last_refresh=snapshot.last_refresh,
        last_verified_at=last_verified_at,
    )
