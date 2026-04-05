from __future__ import annotations

import base64
import json
import re
import secrets
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import __version__
from .errors import InvalidPassphraseError, InvalidTransferFileError
from .models import AccountMetadata, AccountSnapshot, TransferAccount, TransferArchive
from .validators import parse_snapshot, validate_account_name

FORMAT_VERSION = 1
KDF_NAME = "scrypt"
CIPHER_NAME = "aesgcm"
KEY_LENGTH = 32
SALT_LENGTH = 16
NONCE_LENGTH = 12
MAX_BLOB_BYTES = 1024 * 1024
MAX_ACCOUNT_COUNT = 100
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
KDF_PARAMS_V1 = {
    "length": KEY_LENGTH,
    "n": SCRYPT_N,
    "r": SCRYPT_R,
    "p": SCRYPT_P,
}
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PASSHRASE_ERROR_MESSAGE = "invalid passphrase or corrupted file"
UNSUPPORTED_VERSION_MESSAGE = "unsupported transfer format version"
INVALID_FILE_MESSAGE = "invalid transfer file"


def encrypt_transfer_archive(
    accounts: Iterable[TransferAccount],
    *,
    passphrase: str,
    format_version: int = FORMAT_VERSION,
    exported_at: str | None = None,
    tool_version: str | None = __version__,
) -> bytes:
    if format_version != FORMAT_VERSION:
        raise ValueError(UNSUPPORTED_VERSION_MESSAGE)

    accounts = list(accounts)
    if len(accounts) > MAX_ACCOUNT_COUNT:
        raise ValueError("too many accounts for transfer archive")

    salt = secrets.token_bytes(SALT_LENGTH)
    nonce = secrets.token_bytes(NONCE_LENGTH)
    key = _build_kdf(salt).derive(passphrase.encode("utf-8"))
    payload = {
        "exported_at": _validate_optional_timestamp_value(exported_at, field_name="exported_at"),
        "tool_version": _validate_optional_metadata_value(tool_version, field_name="tool_version"),
        "accounts": [_serialize_transfer_account(account) for account in accounts],
    }
    plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    envelope = {
        "format_version": format_version,
        "kdf": KDF_NAME,
        "kdf_params": {
            "salt": _b64encode(salt),
            **KDF_PARAMS_V1,
        },
        "cipher": CIPHER_NAME,
        "nonce": _b64encode(nonce),
        "ciphertext": _b64encode(ciphertext),
    }
    blob = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(blob) > MAX_BLOB_BYTES:
        raise ValueError("transfer archive exceeds size limit")
    return blob


def decrypt_transfer_archive(blob: bytes, *, passphrase: str) -> TransferArchive:
    if len(blob) > MAX_BLOB_BYTES:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    envelope = _load_json_object(blob)
    format_version = envelope.get("format_version")
    if format_version != FORMAT_VERSION:
        raise InvalidTransferFileError(UNSUPPORTED_VERSION_MESSAGE)

    kdf_name = _require_string(envelope, "kdf")
    if kdf_name != KDF_NAME:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    cipher_name = _require_string(envelope, "cipher")
    if cipher_name != CIPHER_NAME:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    kdf_params = _require_mapping(envelope, "kdf_params")
    salt = _validate_kdf_params(kdf_params)
    nonce = _b64decode_required(envelope, "nonce", expected_length=NONCE_LENGTH)
    ciphertext = _b64decode_required(envelope, "ciphertext")

    try:
        key = _build_kdf(salt).derive(passphrase.encode("utf-8"))
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise InvalidPassphraseError(PASSHRASE_ERROR_MESSAGE) from None
    except ValueError:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None

    payload = _load_json_object(plaintext)
    accounts_payload = _require_list(payload, "accounts")
    if len(accounts_payload) > MAX_ACCOUNT_COUNT:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    accounts = [_deserialize_transfer_account(item) for item in accounts_payload]
    return TransferArchive(
        format_version=format_version,
        kdf=kdf_name,
        kdf_params=dict(kdf_params),
        cipher=cipher_name,
        nonce=nonce,
        ciphertext=ciphertext,
        accounts=accounts,
        exported_at=_optional_timestamp_string(payload, "exported_at"),
        tool_version=_optional_string(payload, "tool_version"),
    )


def _build_kdf(salt: bytes) -> Scrypt:
    return Scrypt(
        salt=salt,
        length=KEY_LENGTH,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )


def _serialize_transfer_account(account: TransferAccount) -> dict[str, Any]:
    _validate_transfer_account(account)
    return {
        "name": account.name,
        "metadata": asdict(account.metadata),
        "snapshot": {
            "auth_mode": account.snapshot.auth_mode,
            "account_id": account.snapshot.account_id,
            "last_refresh": account.snapshot.last_refresh,
            "raw": account.snapshot.raw,
        },
    }


def _deserialize_transfer_account(data: Any) -> TransferAccount:
    mapping = _require_mapping(data)
    name = _require_string(mapping, "name")
    metadata_data = _require_mapping(mapping, "metadata")
    snapshot_data = _require_mapping(mapping, "snapshot")
    metadata_name = _require_string(metadata_data, "name")
    raw = dict(_require_mapping(snapshot_data, "raw"))

    try:
        validated_name = validate_account_name(name)
        parsed_snapshot = parse_snapshot(raw)
    except ValueError:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None

    if metadata_name != validated_name:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    if _require_string(metadata_data, "auth_mode") != parsed_snapshot.auth_mode:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if _require_string(metadata_data, "account_id") != parsed_snapshot.account_id:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if _optional_string(metadata_data, "last_refresh") != parsed_snapshot.last_refresh:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    if _require_string(snapshot_data, "auth_mode") != parsed_snapshot.auth_mode:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if _require_string(snapshot_data, "account_id") != parsed_snapshot.account_id:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if _optional_string(snapshot_data, "last_refresh") != parsed_snapshot.last_refresh:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    metadata = AccountMetadata(
        name=validated_name,
        auth_mode=parsed_snapshot.auth_mode,
        account_id=parsed_snapshot.account_id,
        created_at=_require_timestamp_string(metadata_data, "created_at"),
        updated_at=_require_timestamp_string(metadata_data, "updated_at"),
        last_refresh=parsed_snapshot.last_refresh,
        last_verified_at=_optional_timestamp_string(metadata_data, "last_verified_at"),
    )
    snapshot = AccountSnapshot(
        auth_mode=parsed_snapshot.auth_mode,
        account_id=parsed_snapshot.account_id,
        last_refresh=parsed_snapshot.last_refresh,
        raw=parsed_snapshot.raw,
    )
    return TransferAccount(name=validated_name, metadata=metadata, snapshot=snapshot)


def _validate_transfer_account(account: TransferAccount) -> None:
    try:
        validated_name = validate_account_name(account.name)
        parsed_snapshot = parse_snapshot(account.snapshot.raw)
        _parse_iso_timestamp(account.metadata.created_at)
        _parse_iso_timestamp(account.metadata.updated_at)
        if account.metadata.last_verified_at is not None:
            _parse_iso_timestamp(account.metadata.last_verified_at)
    except ValueError:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None

    if account.metadata.name != validated_name:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if account.metadata.auth_mode != parsed_snapshot.auth_mode:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if account.metadata.account_id != parsed_snapshot.account_id:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if account.metadata.last_refresh != parsed_snapshot.last_refresh:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)

    if account.snapshot.auth_mode != parsed_snapshot.auth_mode:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if account.snapshot.account_id != parsed_snapshot.account_id:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    if account.snapshot.last_refresh != parsed_snapshot.last_refresh:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)


def _validate_optional_metadata_value(value: Any, *, field_name: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{field_name} must be a string or None")


def _validate_optional_timestamp_value(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or None")
    _parse_iso_timestamp(value)
    return value


def _load_json_object(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None
    return _require_mapping(value)


def _require_mapping(data: Any, key: str | None = None) -> dict[str, Any]:
    value = data if key is None else data.get(key)
    if not isinstance(value, dict):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    return value


def _require_list(data: Any, key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    return value


def _require_string(data: Any, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    return value


def _require_timestamp_string(data: Any, key: str) -> str:
    value = _require_string(data, key)
    try:
        _parse_iso_timestamp(value)
    except ValueError:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None
    return value


def _optional_string(data: Any, key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    return value


def _optional_timestamp_string(data: Any, key: str) -> str | None:
    value = _optional_string(data, key)
    if value is None:
        return None
    try:
        _parse_iso_timestamp(value)
    except ValueError:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None
    return value


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _parse_iso_timestamp(value: str) -> datetime:
    if not UTC_TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("timestamp must use canonical UTC Z format")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_kdf_params(kdf_params: dict[str, Any]) -> bytes:
    if set(kdf_params) != {"salt", *KDF_PARAMS_V1}:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    for key, expected in KDF_PARAMS_V1.items():
        if kdf_params.get(key) != expected:
            raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    return _b64decode_required(kdf_params, "salt", expected_length=SALT_LENGTH)


def _b64decode_required(data: dict[str, Any], key: str, *, expected_length: int | None = None) -> bytes:
    value = data.get(key)
    if not isinstance(value, str):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE) from None
    if expected_length is not None and len(decoded) != expected_length:
        raise InvalidTransferFileError(INVALID_FILE_MESSAGE)
    return decoded
