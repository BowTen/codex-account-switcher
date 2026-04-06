from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from codex_auth.errors import InteractiveRequiredError
from codex_auth.models import AccountMetadata, ImportPlanItem, TransferAccount
from codex_auth import prompts


class _FakePrompt:
    def __init__(self, value=None, *, responses=None, validate=None, filter=None):  # type: ignore[no-untyped-def]
        self.value = value
        self.responses = list(responses or [])
        self.validate = validate
        self.filter = filter

    def execute(self):  # type: ignore[no-untyped-def]
        if self.responses:
            for response in self.responses:
                if self.validate is not None:
                    result = self.validate(response)
                    if result not in (True, None):
                        continue
                return self.filter(response) if self.filter is not None else response
            raise AssertionError("prompt did not accept any provided responses")
        return self.filter(self.value) if self.filter is not None else self.value


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


def test_require_interactive_uses_sys_stdin_at_call_time(monkeypatch) -> None:
    class InteractiveStdin:
        def isatty(self) -> bool:
            return True

    class NonInteractiveStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", InteractiveStdin())
    reloaded_prompts = importlib.reload(prompts)
    monkeypatch.setattr(sys, "stdin", NonInteractiveStdin())

    with pytest.raises(InteractiveRequiredError, match="export requires an interactive terminal"):
        reloaded_prompts.require_interactive("export")


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

    def fake_text(*, message, default, validate=None, invalid_message=None, filter=None):  # type: ignore[no-untyped-def]
        captured["message"] = message
        captured["default"] = default
        return _FakePrompt(" ~/exports/accounts.codex \n", filter=filter)

    monkeypatch.setattr(prompts.inquirer, "text", fake_text)

    result = prompts.prompt_export_path(Path("/tmp/default.codex"))

    assert result == Path("~/exports/accounts.codex").expanduser()
    assert captured["message"] == "Export file path"
    assert captured["default"] == "/tmp/default.codex"


def test_prompt_export_path_rejects_blank_input_before_accepting_value(monkeypatch) -> None:
    captured = {}

    def fake_text(*, message, default, validate=None, invalid_message=None, filter=None):  # type: ignore[no-untyped-def]
        captured["message"] = message
        captured["default"] = default
        captured["validate"] = validate
        captured["invalid_message"] = invalid_message
        captured["filter"] = filter
        return _FakePrompt(responses=["   ", " ~/exports/accounts.codex \n"], validate=validate, filter=filter)

    monkeypatch.setattr(prompts.inquirer, "text", fake_text)

    result = prompts.prompt_export_path(Path("/tmp/default.codex"))

    assert result == Path("~/exports/accounts.codex").expanduser()
    assert captured["message"] == "Export file path"
    assert captured["default"] == "/tmp/default.codex"
    assert captured["validate"] is not None
    assert captured["invalid_message"]


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


def test_prompt_new_account_name_rejects_blank_and_invalid_input(monkeypatch) -> None:
    captured = {}

    def fake_text(*, message, validate=None, invalid_message=None, filter=None, default=None):  # type: ignore[no-untyped-def]
        captured["message"] = message
        captured["validate"] = validate
        captured["invalid_message"] = invalid_message
        captured["filter"] = filter
        return _FakePrompt(responses=["   ", "bad name", "  vacation  "], validate=validate, filter=filter)

    monkeypatch.setattr(prompts.inquirer, "text", fake_text)

    result = prompts.prompt_new_account_name("work")

    assert result == "vacation"
    assert captured["message"] == "Rename imported account 'work' to"
    assert captured["validate"] is not None
    assert captured["invalid_message"]


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


def test_build_import_plan_reprompts_until_unique_rename_target(monkeypatch) -> None:
    archive_accounts = [
        make_transfer_account("work", "acct-work"),
        make_transfer_account("travel", "acct-travel"),
    ]
    existing_accounts = [make_metadata("work", "acct-work"), make_metadata("travel", "acct-travel")]

    monkeypatch.setattr(prompts, "prompt_conflict_action", lambda name: "rename")
    responses = iter(["shared", "shared", "vacation"])
    calls: list[str] = []

    def fake_prompt_new_account_name(source_name: str) -> str:
        calls.append(source_name)
        return next(responses)

    monkeypatch.setattr(prompts, "prompt_new_account_name", fake_prompt_new_account_name)

    plan = prompts.build_import_plan(
        archive_accounts,
        existing_accounts,
        {"work", "travel"},
    )

    assert plan == [
        ImportPlanItem(source_name="work", target_name="shared", action="rename"),
        ImportPlanItem(source_name="travel", target_name="vacation", action="rename"),
    ]
    assert calls == ["work", "travel", "travel"]


def test_build_import_plan_rejects_duplicate_import_targets_from_repeated_archive_names() -> None:
    archive_accounts = [
        make_transfer_account("work", "acct-work-1"),
        make_transfer_account("work", "acct-work-2"),
    ]

    with pytest.raises(ValueError, match="Duplicate import target name: work"):
        prompts.build_import_plan(
            archive_accounts,
            [],
            {"work"},
        )
