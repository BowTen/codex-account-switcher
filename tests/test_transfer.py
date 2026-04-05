from __future__ import annotations

import json

import pytest

from codex_auth.errors import InvalidPassphraseError, InvalidTransferFileError
from codex_auth.models import AccountMetadata, AccountSnapshot, TransferAccount
from codex_auth.transfer import decrypt_transfer_archive, encrypt_transfer_archive


def make_transfer_account(name: str, account_id: str) -> TransferAccount:
    metadata = AccountMetadata(
        name=name,
        auth_mode="chatgpt",
        account_id=account_id,
        created_at="2026-04-05T10:00:00Z",
        updated_at="2026-04-05T10:00:00Z",
        last_refresh="2026-04-05T09:00:00Z",
    )
    snapshot = AccountSnapshot(
        auth_mode="chatgpt",
        account_id=account_id,
        last_refresh="2026-04-05T09:00:00Z",
        raw={
            "auth_mode": "chatgpt",
            "last_refresh": "2026-04-05T09:00:00Z",
            "tokens": {
                "access_token": f"access-{account_id}",
                "refresh_token": f"refresh-{account_id}",
                "id_token": f"id-{account_id}",
                "account_id": account_id,
            },
        },
    )
    return TransferAccount(name=name, metadata=metadata, snapshot=snapshot)


def test_encrypt_and_decrypt_transfer_archive_round_trip() -> None:
    payload = [make_transfer_account("work", "acct-work"), make_transfer_account("personal", "acct-personal")]

    blob = encrypt_transfer_archive(payload, passphrase="correct horse battery staple")
    restored = decrypt_transfer_archive(blob, passphrase="correct horse battery staple")

    assert restored.format_version == 1
    assert restored.kdf == "scrypt"
    assert restored.cipher == "aesgcm"
    assert [account.name for account in restored.accounts] == ["work", "personal"]
    assert restored.accounts[0].metadata.account_id == "acct-work"
    assert restored.accounts[1].snapshot.raw["tokens"]["refresh_token"] == "refresh-acct-personal"


def test_decrypt_transfer_archive_rejects_wrong_passphrase() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")

    with pytest.raises(InvalidPassphraseError, match="invalid passphrase or corrupted file"):
        decrypt_transfer_archive(blob, passphrase="wrong passphrase")


def test_decrypt_transfer_archive_rejects_unsupported_format_version() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    envelope = json.loads(blob)
    envelope["format_version"] = 99
    tampered_blob = json.dumps(envelope).encode("utf-8")

    with pytest.raises(InvalidTransferFileError, match="unsupported transfer format version"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")
