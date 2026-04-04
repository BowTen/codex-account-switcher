from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .models import AccountMetadata, AccountSnapshot


NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SUPPORTED_AUTH_MODES = {"chatgpt"}


def utc_now_iso() -> str:
    value = datetime.now(UTC).replace(microsecond=0).isoformat()
    return value.replace("+00:00", "Z")


def validate_account_name(name: str) -> str:
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid account name: {name!r}")
    return name


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_snapshot(raw: dict[str, Any]) -> AccountSnapshot:
    if not isinstance(raw, dict):
        raise ValueError("Missing or invalid snapshot root")

    auth_mode = raw.get("auth_mode")
    tokens = raw.get("tokens")
    if not isinstance(auth_mode, str) or auth_mode not in SUPPORTED_AUTH_MODES:
        raise ValueError(f"Unsupported auth_mode: {auth_mode!r}")
    if not isinstance(tokens, dict):
        raise ValueError("Missing or invalid tokens")

    required = ("access_token", "refresh_token", "id_token", "account_id")
    missing = [key for key in required if not _is_nonempty_string(tokens.get(key))]
    if missing:
        raise ValueError(f"Missing required token fields: {', '.join(missing)}")

    last_refresh = raw.get("last_refresh")
    if last_refresh is not None and not isinstance(last_refresh, str):
        raise ValueError("Invalid last_refresh")

    return AccountSnapshot(
        auth_mode=auth_mode,
        account_id=tokens["account_id"],
        last_refresh=last_refresh,
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
