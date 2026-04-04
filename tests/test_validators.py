import pytest

from codex_auth.validators import parse_snapshot, validate_account_name


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


def test_validate_account_name_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="Invalid account name"):
        validate_account_name("work account")
