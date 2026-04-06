from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from codex_auth.errors import InvalidPassphraseError, InvalidTransferFileError, TransferError
from codex_auth.models import AccountMetadata, AccountSnapshot, TransferAccount
from codex_auth import transfer as transfer_module
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


def rewrite_encrypted_payload(
    blob: bytes, *, passphrase: str, mutate_payload  # type: ignore[no-untyped-def]
) -> bytes:
    envelope = json.loads(blob)
    params = envelope["kdf_params"]
    salt = base64.b64decode(params["salt"])
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    key = Scrypt(
        salt=salt,
        length=params["length"],
        n=params["n"],
        r=params["r"],
        p=params["p"],
    ).derive(passphrase.encode("utf-8"))
    payload = json.loads(AESGCM(key).decrypt(nonce, ciphertext, None))
    mutate_payload(payload)
    envelope["ciphertext"] = base64.b64encode(
        AESGCM(key).encrypt(nonce, json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"), None)
    ).decode("ascii")
    return json.dumps(envelope).encode("utf-8")


def test_encrypt_and_decrypt_transfer_archive_round_trip() -> None:
    payload = [make_transfer_account("work", "acct-work"), make_transfer_account("personal", "acct-personal")]

    blob = encrypt_transfer_archive(
        payload,
        passphrase="correct horse battery staple",
        exported_at="2026-04-05T11:00:00Z",
        tool_version="0.1.0-test",
    )
    restored = decrypt_transfer_archive(blob, passphrase="correct horse battery staple")

    assert restored.exported_at == "2026-04-05T11:00:00Z"
    assert restored.tool_version == "0.1.0-test"
    assert [account.name for account in restored.accounts] == ["work", "personal"]
    assert restored.accounts[0].metadata.account_id == "acct-work"
    assert restored.accounts[1].snapshot.raw["tokens"]["refresh_token"] == "refresh-acct-personal"


def test_encrypt_and_decrypt_transfer_archive_preserves_whitespace_surrounded_passphrase() -> None:
    payload = [make_transfer_account("work", "acct-work")]
    passphrase = "  correct horse battery staple  "

    blob = encrypt_transfer_archive(payload, passphrase=passphrase)
    restored = decrypt_transfer_archive(blob, passphrase=passphrase)

    assert [account.name for account in restored.accounts] == ["work"]


@pytest.mark.parametrize("passphrase", ["", "   "])
def test_encrypt_transfer_archive_rejects_blank_passphrase(passphrase: str) -> None:
    with pytest.raises(ValueError, match="passphrase must not be blank"):
        encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase=passphrase)


def test_decrypt_transfer_archive_rejects_wrong_passphrase() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")

    with pytest.raises(InvalidPassphraseError, match="invalid passphrase or corrupted file"):
        decrypt_transfer_archive(blob, passphrase="wrong passphrase")


@pytest.mark.parametrize("passphrase", ["", "   "])
def test_decrypt_transfer_archive_rejects_blank_passphrase(passphrase: str) -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")

    with pytest.raises(ValueError, match="passphrase must not be blank"):
        decrypt_transfer_archive(blob, passphrase=passphrase)


def test_decrypt_transfer_archive_rejects_duplicate_account_names() -> None:
    blob = encrypt_transfer_archive(
        [make_transfer_account("work", "acct-work"), make_transfer_account("personal", "acct-personal")],
        passphrase="correct horse battery staple",
    )
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: (
            payload["accounts"][1].__setitem__("name", "work"),
            payload["accounts"][1]["metadata"].__setitem__("name", "work"),
        ),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_unsupported_format_version() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    envelope = json.loads(blob)
    envelope["format_version"] = 99
    tampered_blob = json.dumps(envelope).encode("utf-8")

    with pytest.raises(InvalidTransferFileError, match="unsupported transfer format version"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_malformed_nonce_as_invalid_file() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    envelope = json.loads(blob)
    envelope["nonce"] = "AA=="
    tampered_blob = json.dumps(envelope).encode("utf-8")

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_tampered_kdf_params_as_invalid_file() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    envelope = json.loads(blob)
    envelope["kdf_params"]["n"] = 2
    tampered_blob = json.dumps(envelope).encode("utf-8")

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_encrypt_transfer_archive_rejects_unsupported_format_version() -> None:
    with pytest.raises(ValueError, match="unsupported transfer format version"):
        encrypt_transfer_archive(
            [make_transfer_account("work", "acct-work")],
            passphrase="correct horse battery staple",
            format_version=99,
        )


def test_decrypt_transfer_archive_rejects_non_utf8_blob_as_invalid_file() -> None:
    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(b"\xff", passphrase="correct horse battery staple")


def test_transfer_errors_follow_value_error_hierarchy() -> None:
    assert issubclass(TransferError, ValueError)
    assert issubclass(InvalidTransferFileError, ValueError)
    assert issubclass(InvalidPassphraseError, ValueError)


def test_encrypt_transfer_archive_rejects_invalid_account_name() -> None:
    account = make_transfer_account("work", "acct-work")
    account.name = "bad name"
    account.metadata.name = "bad name"

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        encrypt_transfer_archive([account], passphrase="correct horse battery staple")


def test_encrypt_transfer_archive_rejects_metadata_identity_drift() -> None:
    account = make_transfer_account("work", "acct-work")
    account.metadata.account_id = "acct-other"

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        encrypt_transfer_archive([account], passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_tampered_invalid_account_name_in_payload() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: (
            payload["accounts"][0].__setitem__("name", "bad name"),
            payload["accounts"][0]["metadata"].__setitem__("name", "bad name"),
        ),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_tampered_metadata_identity_drift() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: payload["accounts"][0]["metadata"].__setitem__("account_id", "acct-other"),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_invalid_exported_at_type() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: payload.__setitem__("exported_at", 123),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_invalid_tool_version_type() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: payload.__setitem__("tool_version", ["0.1.0"]),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_non_iso_exported_at() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: payload.__setitem__("exported_at", "definitely-not-a-timestamp"),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_date_only_exported_at() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: payload.__setitem__("exported_at", "2026-04-05"),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_naive_exported_at() -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    tampered_blob = rewrite_encrypted_payload(
        blob,
        passphrase="correct horse battery staple",
        mutate_payload=lambda payload: payload.__setitem__("exported_at", "2026-04-05T11:00:00"),
    )

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(tampered_blob, passphrase="correct horse battery staple")


def test_encrypt_transfer_archive_rejects_date_only_metadata_timestamp() -> None:
    account = make_transfer_account("work", "acct-work")
    account.metadata.created_at = "2026-04-05"

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        encrypt_transfer_archive([account], passphrase="correct horse battery staple")


def test_encrypt_transfer_archive_rejects_naive_metadata_timestamp() -> None:
    account = make_transfer_account("work", "acct-work")
    account.metadata.updated_at = "2026-04-05T10:00:00"

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        encrypt_transfer_archive([account], passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_blob_over_size_limit(monkeypatch) -> None:
    blob = encrypt_transfer_archive([make_transfer_account("work", "acct-work")], passphrase="correct horse battery staple")
    monkeypatch.setattr(transfer_module, "MAX_BLOB_BYTES", len(blob) - 1)

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(blob, passphrase="correct horse battery staple")


def test_encrypt_transfer_archive_rejects_blob_over_size_limit() -> None:
    account = make_transfer_account("work", "acct-work")
    account.snapshot.raw["tokens"]["access_token"] = "x" * transfer_module.MAX_BLOB_BYTES

    with pytest.raises(ValueError, match="transfer archive exceeds size limit"):
        encrypt_transfer_archive([account], passphrase="correct horse battery staple")


def test_decrypt_transfer_archive_rejects_account_count_over_limit(monkeypatch) -> None:
    blob = encrypt_transfer_archive(
        [make_transfer_account("work", "acct-work"), make_transfer_account("personal", "acct-personal")],
        passphrase="correct horse battery staple",
    )
    monkeypatch.setattr(transfer_module, "MAX_ACCOUNT_COUNT", 1)

    with pytest.raises(InvalidTransferFileError, match="invalid transfer file"):
        decrypt_transfer_archive(blob, passphrase="correct horse battery staple")
