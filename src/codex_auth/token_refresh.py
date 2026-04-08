from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
import urllib.parse
import urllib.request

from .models import TokenRefreshResult

OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_REFRESH_SKEW_SECONDS = 300


def access_token_needs_refresh(
    access_token: str,
    *,
    now: datetime | None = None,
    skew_seconds: int = DEFAULT_REFRESH_SKEW_SECONDS,
) -> bool:
    payload = _decode_jwt_payload(access_token)
    if payload is None:
        return False

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return False

    current = now or datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    return expires_at <= current + timedelta(seconds=skew_seconds)


def refresh_chatgpt_credentials(
    *,
    access_token: str,
    refresh_token: str,
    id_token: str,
    account_id: str,
    fetch_json: Callable[..., Mapping[str, Any]] | None = None,
) -> TokenRefreshResult:
    fetch = fetch_json or _post_form_json
    try:
        response = fetch(
            OAUTH_TOKEN_URL,
            data={
                "client_id": OAUTH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "content-type": "application/x-www-form-urlencoded",
            },
        )
    except urllib.error.HTTPError as exc:
        raise ValueError(f"refresh request failed: {exc.code} {exc.reason}") from None
    except urllib.error.URLError as exc:
        raise ValueError(f"refresh request failed: {exc.reason}") from None
    if not isinstance(response, Mapping):
        raise ValueError("refresh response was not a JSON object")

    new_access_token = _required_string(response.get("access_token"), field_name="access_token")
    new_refresh_token = _string_or_default(response.get("refresh_token"), refresh_token, field_name="refresh_token")
    new_id_token = _string_or_default(response.get("id_token"), id_token, field_name="id_token")
    new_account_id = _account_id_from_id_token(new_id_token) or account_id

    expires_in = response.get("expires_in")
    expires_in_value = int(expires_in) if isinstance(expires_in, (int, float)) else None
    expires_at = None
    if expires_in_value is not None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in_value)
        ).isoformat().replace("+00:00", "Z")

    return TokenRefreshResult(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        id_token=new_id_token,
        account_id=new_account_id,
        expires_in=expires_in_value,
        expires_at=expires_at,
        raw=dict(response),
    )


def _post_form_json(url: str, *, data: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    for key, value in headers.items():
        req.add_header(key, value)
    req.add_header("accept", "application/json")
    req.add_header("user-agent", "codex-cli/1.0.0")
    try:
        with urllib.request.urlopen(req) as response:
            body = response.read()
        payload = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"refresh request failed: {exc.code} {exc.reason}") from None
    except urllib.error.URLError as exc:
        raise ValueError(f"refresh request failed: {exc.reason}") from None
    except json.JSONDecodeError:
        raise ValueError("refresh request returned invalid JSON") from None
    if not isinstance(payload, Mapping):
        raise ValueError("refresh response was not a JSON object")
    return payload


def _decode_jwt_payload(token: str) -> Mapping[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = _base64url_decode(parts[1])
        decoded = json.loads(payload.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(decoded, Mapping):
        return None
    return decoded


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _account_id_from_id_token(id_token: str) -> str | None:
    payload = _decode_jwt_payload(id_token)
    if payload is None:
        return None
    for key in ("account_id", "https://chatgpt.com/account_id", "https://chat.openai.com/account_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _string_or_default(value: Any, default: str, *, field_name: str) -> str:
    if value is None:
        return default
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"refresh response field {field_name} must be a non-empty string")


def _required_string(value: Any, *, field_name: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"refresh response missing required field {field_name}")
