from __future__ import annotations

from pathlib import Path

import pytest

from codex_auth.errors import InteractiveRequiredError
from codex_auth.models import AccountMetadata, ImportPlanItem, TransferAccount
from codex_auth import prompts


class _FakePrompt:
    def __init__(self, value):
        self.value = value

    def execute(self):  # type: ignore[no-untyped-def]
        return self.value


def make_metadata(name: str, account_id: str) -> AccountMetadata:
    return AccountMetadata(
        name=name,
        auth_mode="chatgpt",
        account_id=account_id,
        created_at="2026-04-04T10:00:00Z",
        updated_at="2026-04-04T10:00:00Z",
        last_refresh="2026-04-04T10:00:00Z",
        last_verified_at=None,
    )


def make_transfer_account(name: str, account_id: str) -> TransferAccount:
    metadata = make_metadata(name, account_id)
    return TransferAccount(
        name=name,
        metadata=metadata,
        snapshot=pytest.importorskip("codex_auth.validators").parse_snapshot(
            {
                "auth_mode": "chatgpt",
                "last_refresh": "2026-04-04T10:00:00Z",
                "tokens": {
                    "access_token": f"access-{account_id}",
                    "refresh_token": f"refresh-{account_id}",
                    "id_token": f"id-{account_id}",
                    "account_id": account_id,
                },
            }
        ),
    )


def test_require_interactive_rejects_noninteractive_stdin() -> None:
    class FakeStdin:
        def isatty(self) -> bool:
            return False

    with pytest.raises(InteractiveRequiredError, match="export requires an interactive terminal"):
        prompts.require_interactive("export", stdin=FakeStdin())


def test_prompt_select_saved_accounts_uses_inquirer_checkbox(monkeypatch) -> None:
    accounts = [make_metadata("work", "acct-work"), make_metadata("personal", "acct-personal")]
    captured = {}

    def fake_checkbox(*, message, choices, instruction):  # type: ignore[no-untyped-def]
        captured["message"] = message
        captured["choices"] = choices
        captured["instruction"] = instruction
        return _FakePrompt(["personal", "work"])

    monkeypatch.setattr(prompts.inquirer, "checkbox", fake_checkbox)

    result = prompts.prompt_select_saved_accounts(accounts, message="Select accounts to export")

    assert result == ["personal", "work"]
    assert captured["message"] == "Select accounts to export"
    assert captured["instruction"]
    assert [choice.value for choice in captured["choices"]] == ["work", "personal"]
    assert [choice.name for choice in captured["choices"]] == [
        "work  chatgpt  acct-work",
        "personal  chatgpt  acct-personal",
    ]


def test_prompt_select_archive_accounts_uses_inquirer_checkbox(monkeypatch) -> None:
    accounts = [make_transfer_account("work", "acct-work"), make_transfer_account("travel", "acct-travel")]
    captured = {}

    def fake_checkbox(*, message, choices, instruction):  # type: ignore[no-untyped-def]
        captured["message"] = message
        captured["choices"] = choices
        captured["instruction"] = instruction
        return _FakePrompt(["travel"])

    monkeypatch.setattr(prompts.inquirer, "checkbox", fake_checkbox)

    result = prompts.prompt_select_archive_accounts(accounts)

    assert result == ["travel"]
    assert captured["message"] == "Select accounts to import"
    assert captured["instruction"]
    assert [choice.value for choice in captured["choices"]] == ["work", "travel"]


def test_prompt_export_path_expands_user_and_trims_whitespace(monkeypatch) -> None:
    captured = {}

    def fake_text(*, message, default):  # type: ignore[no-untyped-def]
        captured["message"] = message
        captured["default"] = default
        return _FakePrompt(" ~/exports/accounts.codex \n")

    monkeypatch.setattr(prompts.inquirer, "text", fake_text)

    result = prompts.prompt_export_path(Path("/tmp/default.codex"))

    assert result == Path("~/exports/accounts.codex").expanduser()
    assert captured["message"] == "Export file path"
    assert captured["default"] == "/tmp/default.codex"


def test_prompt_passphrase_confirms_matching_values(monkeypatch) -> None:
    prompts_seen: list[str] = []

    def fake_secret(*, message):  # type: ignore[no-untyped-def]
        prompts_seen.append(message)
        return _FakePrompt("correct horse battery staple")

    monkeypatch.setattr(prompts.inquirer, "secret", fake_secret)

    result = prompts.prompt_passphrase(confirm=True)

    assert result == "correct horse battery staple"
    assert prompts_seen == ["Passphrase", "Confirm passphrase"]


def test_prompt_passphrase_rejects_mismatched_confirmation(monkeypatch) -> None:
    responses = iter(["one", "two"])

    def fake_secret(*, message):  # type: ignore[no-untyped-def]
        return _FakePrompt(next(responses))

    monkeypatch.setattr(prompts.inquirer, "secret", fake_secret)

    with pytest.raises(ValueError, match="Passphrases do not match"):
        prompts.prompt_passphrase(confirm=True)


def test_build_import_plan_preserves_archive_order_and_actions(monkeypatch) -> None:
    archive_accounts = [
        make_transfer_account("work", "acct-work"),
        make_transfer_account("travel", "acct-travel"),
        make_transfer_account("personal", "acct-personal"),
    ]
    existing_accounts = [
        make_metadata("work", "acct-work"),
        make_metadata("travel", "acct-travel"),
        make_metadata("personal", "acct-personal"),
    ]

    conflict_actions = iter(["overwrite", "rename", "skip"])

    def fake_conflict_action(name: str) -> str:
        return next(conflict_actions)

    monkeypatch.setattr(prompts, "prompt_conflict_action", fake_conflict_action)
    monkeypatch.setattr(prompts, "prompt_new_account_name", lambda source_name: "vacation")

    plan = prompts.build_import_plan(
        archive_accounts,
        existing_accounts,
        {"work", "travel", "personal"},
    )

    assert plan == [
        ImportPlanItem(source_name="work", target_name="work", action="overwrite"),
        ImportPlanItem(source_name="travel", target_name="vacation", action="rename"),
        ImportPlanItem(source_name="personal", target_name="personal", action="skip"),
    ]


def test_build_import_plan_rejects_duplicate_planned_target_names(monkeypatch) -> None:
    archive_accounts = [
        make_transfer_account("work", "acct-work"),
        make_transfer_account("travel", "acct-travel"),
    ]
    existing_accounts = [make_metadata("work", "acct-work"), make_metadata("travel", "acct-travel")]

    monkeypatch.setattr(prompts, "prompt_conflict_action", lambda name: "rename")
    monkeypatch.setattr(prompts, "prompt_new_account_name", lambda source_name: "shared")

    with pytest.raises(ValueError, match="Account already exists: shared"):
        prompts.build_import_plan(
            archive_accounts,
            existing_accounts,
            {"work", "travel"},
        )
