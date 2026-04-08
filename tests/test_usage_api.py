from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from codex_auth.models import TokenRefreshResult, UsageSnapshot


def test_parse_usage_payload_normalizes_primary_secondary_and_credits() -> None:
    from codex_auth.usage_api import parse_usage_payload

    payload = {
        "plan_type": "chatgpt_plus",
        "rate_limit": {
            "primary_window": {
                "used_percent": 12.5,
                "limit_window_seconds": 18000,
                "reset_at": 1712570400,
            },
            "secondary_window": {
                "used_percent": 70,
                "limit_window_seconds": 604800,
                "reset_at": 1713175200,
            },
        },
        "credits": {
            "has_credits": True,
            "unlimited": False,
            "balance": "0",
        },
    }

    snapshot = parse_usage_payload(payload, account_id="acct-123")

    assert snapshot.plan_type == "chatgpt_plus"
    assert snapshot.account_id == "acct-123"
    assert snapshot.primary_window.used_percent == 12.5
    assert snapshot.primary_window.limit_window_seconds == 18000
    assert snapshot.primary_window.reset_at == 1712570400
    assert snapshot.secondary_window.used_percent == 70
    assert snapshot.secondary_window.limit_window_seconds == 604800
    assert snapshot.secondary_window.reset_at == 1713175200
    assert snapshot.credits.has_credits is True
    assert snapshot.credits.unlimited is False
    assert snapshot.credits.balance == "0"


def test_refresh_credentials_preserves_missing_fields_and_recovers_account_id() -> None:
    from codex_auth.token_refresh import refresh_chatgpt_credentials

    refresh_token = "refresh-token"
    id_payload = {"sub": "acct-123"}
    id_token = ".".join(
        [
            base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("="),
            base64.urlsafe_b64encode(json.dumps(id_payload).encode()).decode().rstrip("="),
            "",
        ]
    )

    response = {
        "access_token": "new-access",
        "expires_in": 3600,
        "id_token": id_token,
    }

    result = refresh_chatgpt_credentials(
        access_token="old-access",
        refresh_token=refresh_token,
        id_token="old-id",
        account_id="acct-old",
        fetch_json=lambda *args, **kwargs: response,
    )

    assert isinstance(result, TokenRefreshResult)
    assert result.access_token == "new-access"
    assert result.refresh_token == refresh_token
    assert result.id_token == id_token
    assert result.account_id == "acct-123"


def test_refresh_credentials_rejects_missing_access_token() -> None:
    from codex_auth.token_refresh import refresh_chatgpt_credentials

    with pytest.raises(ValueError, match="access_token"):
        refresh_chatgpt_credentials(
            access_token="old-access",
            refresh_token="refresh-token",
            id_token="old-id",
            account_id="acct-old",
            fetch_json=lambda *args, **kwargs: {"refresh_token": "new-refresh"},
        )


def test_access_token_needs_refresh_uses_jwt_exp() -> None:
    from codex_auth.token_refresh import access_token_needs_refresh

    token = _make_jwt({"exp": int(datetime(2026, 4, 8, 12, 5, tzinfo=timezone.utc).timestamp())})

    assert access_token_needs_refresh(
        token,
        now=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )


def test_fetch_usage_raises_concise_value_error_for_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_auth import usage_api

    class Response:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

    def fake_urlopen(request):
        raise usage_api.urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=Response(403, b'{"error":"denied"}'),
        )

    monkeypatch.setattr(usage_api.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="usage request failed: 403 Forbidden"):
        usage_api.fetch_usage(
            access_token="token",
            account_id="acct-123",
        )


def test_refresh_request_uses_chatgpt_oauth_endpoint_and_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_auth import token_refresh

    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"new-access","id_token":"new-id","refresh_token":"new-refresh"}'

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["data"] = request.data.decode()
        captured["headers"] = dict(request.header_items())
        return Response()

    monkeypatch.setattr(token_refresh.urllib.request, "urlopen", fake_urlopen)

    token_refresh.refresh_chatgpt_credentials(
        access_token="old-access",
        refresh_token="refresh-token",
        id_token="old-id",
        account_id="acct-old",
    )

    assert captured["url"] == "https://auth.openai.com/oauth/token"
    assert "client_id=app_EMoamEEZ73f0CkXaXp7hrann" in captured["data"]


def test_usage_request_sends_expected_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_auth import usage_api

    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"plan_type":"chatgpt_plus","rate_limit":{"primary_window":{"used_percent":1,"limit_window_seconds":18000,"reset_at":1712570400}},"credits":{"has_credits":true,"unlimited":false,"balance":"0"}}'

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return Response()

    monkeypatch.setattr(usage_api.urllib.request, "urlopen", fake_urlopen)

    usage_api.fetch_usage(access_token="token", account_id="acct-123")

    headers = captured["headers"]
    assert captured["url"] == "https://chatgpt.com/backend-api/wham/usage"
    assert headers["Authorization"] == "Bearer token"
    assert headers["Chatgpt-account-id"] == "acct-123"
    assert headers["User-agent"] == "codex-cli/1.0.0"


def test_refresh_credentials_raises_concise_value_error_for_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from codex_auth import token_refresh

    def fake_urlopen(request):
        raise token_refresh.urllib.error.URLError("timeout")

    monkeypatch.setattr(token_refresh.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="refresh request failed: timeout"):
        token_refresh.refresh_chatgpt_credentials(
            access_token="old-access",
            refresh_token="refresh-token",
            id_token="old-id",
            account_id="acct-old",
        )


def _make_jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none"}
    encoded_header = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{encoded_header}.{encoded_payload}."
