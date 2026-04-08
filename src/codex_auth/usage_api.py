from __future__ import annotations

import json
from typing import Any, Callable, Mapping
import urllib.error
import urllib.request

from .models import UsageCredits, UsageSnapshot, UsageWindow

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


def fetch_usage(
    *,
    access_token: str,
    account_id: str,
    opener: Callable[[urllib.request.Request], Any] | None = None,
) -> UsageSnapshot:
    req = urllib.request.Request(USAGE_URL, method="GET")
    req.add_header("authorization", f"Bearer {access_token}")
    req.add_header("chatgpt-account-id", account_id)
    req.add_header("user-agent", "codex-cli/1.0.0")
    req.add_header("accept", "application/json")

    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"usage request failed: {exc.code} {exc.reason}") from None
    except urllib.error.URLError as exc:
        raise ValueError(f"usage request failed: {exc.reason}") from None
    except json.JSONDecodeError as exc:
        raise ValueError("usage request returned invalid JSON") from None

    if not isinstance(payload, Mapping):
        raise ValueError("usage payload was not a JSON object")
    return parse_usage_payload(payload, account_id=account_id)


def parse_usage_payload(payload: Mapping[str, Any], *, account_id: str = "") -> UsageSnapshot:
    plan_type = _optional_string(payload.get("plan_type"))
    rate_limit = _first_mapping(payload, "rate_limit")
    primary = _parse_window(_first_mapping(rate_limit or {}, "primary_window"))
    secondary = _parse_window(_first_mapping(rate_limit or {}, "secondary_window"))
    credits = _parse_credits(_first_mapping(payload, "credits"))

    if primary is None and secondary is None:
        raise ValueError("usage payload missing rate limit data")

    return UsageSnapshot(
        account_id=account_id,
        plan_type=plan_type,
        primary_window=primary,
        secondary_window=secondary,
        credits=credits,
        raw=dict(payload),
    )


def _parse_window(data: Mapping[str, Any] | None) -> UsageWindow | None:
    if data is None:
        return None
    return UsageWindow(
        used_percent=_optional_number(data.get("used_percent")),
        limit_window_seconds=_optional_int(data.get("limit_window_seconds")),
        reset_at=_optional_reset_at(data.get("reset_at")),
        raw=dict(data),
    )


def _parse_credits(data: Mapping[str, Any] | None) -> UsageCredits | None:
    if data is None:
        return None
    return UsageCredits(
        has_credits=_optional_bool(data.get("has_credits")),
        unlimited=_optional_bool(data.get("unlimited")),
        balance=_optional_balance(data.get("balance")),
        raw=dict(data),
    )


def _first_mapping(payload: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _optional_balance(value: Any) -> float | int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        return value
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_reset_at(value: Any) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, str)) and value != "":
        return value
    return None
