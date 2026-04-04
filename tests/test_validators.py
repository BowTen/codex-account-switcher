import pytest

from codex_auth.validators import build_metadata, parse_snapshot, validate_account_name


def test_parse_snapshot_rejects_invalid_tokens() -> None:
    raw = {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": "not-a-mapping",
    }

    with pytest.raises(ValueError, match="Missing or invalid tokens"):
        parse_snapshot(raw)


def test_parse_snapshot_extracts_required_metadata() -> None:
    raw = {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
            "account_id": "acct-123",
        },
    }

    snapshot = parse_snapshot(raw)

    assert snapshot.auth_mode == "chatgpt"
    assert snapshot.account_id == "acct-123"
    assert snapshot.last_refresh == "2026-04-04T10:00:00Z"


@pytest.mark.parametrize(
    ("tokens", "match"),
    [
        ({"access_token": "", "refresh_token": "refresh", "id_token": "id", "account_id": "acct-123"}, "access_token"),
        ({"refresh_token": "refresh", "id_token": "id", "account_id": "acct-123"}, "access_token"),
    ],
)
def test_parse_snapshot_rejects_missing_required_token_fields(tokens: dict[str, str], match: str) -> None:
    raw = {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": tokens,
    }

    with pytest.raises(ValueError, match=match):
        parse_snapshot(raw)


@pytest.mark.parametrize("auth_mode", ["legacy", "", None])
def test_parse_snapshot_rejects_unsupported_or_invalid_auth_mode(auth_mode: object) -> None:
    raw = {
        "auth_mode": auth_mode,
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
            "account_id": "acct-123",
        },
    }

    with pytest.raises(ValueError, match="auth_mode"):
        parse_snapshot(raw)


@pytest.mark.parametrize("last_refresh", [123, [], {}])
def test_parse_snapshot_rejects_malformed_last_refresh(last_refresh: object) -> None:
    raw = {
        "auth_mode": "chatgpt",
        "last_refresh": last_refresh,
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
            "account_id": "acct-123",
        },
    }

    with pytest.raises(ValueError, match="last_refresh"):
        parse_snapshot(raw)


def test_build_metadata_returns_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("codex_auth.validators.utc_now_iso", lambda: "2026-04-04T11:00:00Z")

    snapshot = parse_snapshot(
        {
            "auth_mode": "chatgpt",
            "last_refresh": "2026-04-04T10:00:00Z",
            "tokens": {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
                "account_id": "acct-123",
            },
        }
    )

    metadata = build_metadata(
        "work",
        snapshot,
        created_at="2026-04-04T09:00:00Z",
        last_verified_at="2026-04-04T12:00:00Z",
    )

    assert metadata.to_dict() == {
        "name": "work",
        "auth_mode": "chatgpt",
        "account_id": "acct-123",
        "created_at": "2026-04-04T09:00:00Z",
        "updated_at": "2026-04-04T11:00:00Z",
        "last_refresh": "2026-04-04T10:00:00Z",
        "last_verified_at": "2026-04-04T12:00:00Z",
    }


def test_validate_account_name_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="Invalid account name"):
        validate_account_name("work account")
