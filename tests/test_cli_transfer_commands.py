from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from codex_auth.cli import main as cli_main
from codex_auth.errors import InteractiveRequiredError
from codex_auth.models import AccountMetadata, ImportPlanItem, TransferAccount
from codex_auth import prompts
from codex_auth.service import CodexAuthService
from codex_auth.transfer import encrypt_transfer_archive


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


def make_snapshot(account_id: str) -> dict[str, object]:
    return {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": f"access-{account_id}",
            "refresh_token": f"refresh-{account_id}",
            "id_token": f"id-{account_id}",
            "account_id": account_id,
        },
    }


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


def test_cli_export_requires_interactive_terminal(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    result = cli_main(["export", "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "error: export requires an interactive terminal" in captured.err


def test_cli_export_writes_encrypted_transfer_file(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    service = CodexAuthService()
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    output_path = tmp_path / "accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_saved_accounts",
        lambda accounts, message: ["work", "personal"],
    )
    monkeypatch.setattr("codex_auth.prompts.prompt_export_path", lambda default_path: output_path)

    result = cli_main(["export", "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 0
    assert output_path.exists()
    assert captured.err == ""
    assert f"exported: 2 accounts -> {output_path}" in captured.out


def test_cli_export_preserves_passphrase_file_whitespace(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    service = CodexAuthService()
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    output_path = tmp_path / "accounts.cae"
    passphrase = "  secret-pass  "
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text(f"{passphrase}\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_saved_accounts",
        lambda accounts, message: ["work"],
    )
    monkeypatch.setattr("codex_auth.prompts.prompt_export_path", lambda default_path: output_path)

    result = cli_main(["export", "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert service.read_import_archive(output_path, passphrase=passphrase).accounts[0].name == "work"


def test_cli_export_empty_selection_is_cancellation(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    service = CodexAuthService()
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_saved_accounts",
        lambda accounts, message: [],
    )

    result = cli_main(["export", "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 3
    assert captured.out == ""
    assert "cancelled: export" in captured.err


def test_cli_export_with_no_saved_accounts_errors_before_reading_passphrase_file(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    missing_pass_file = tmp_path / "missing-pass.txt"

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_saved_accounts",
        lambda accounts, message: (_ for _ in ()).throw(AssertionError("selection prompt should not run")),
    )
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_export_path",
        lambda default_path: (_ for _ in ()).throw(AssertionError("path prompt should not run")),
    )

    result = cli_main(["export", "--passphrase-file", str(missing_pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "error: No saved accounts available for export" in captured.err


def test_cli_export_reports_missing_passphrase_file_concisely(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    service = CodexAuthService()
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    missing_pass_file = tmp_path / "missing-pass.txt"

    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_saved_accounts",
        lambda accounts, message: calls.append(("select", message)) or ["work"],
    )
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_export_path",
        lambda default_path: calls.append(("path", str(default_path))) or tmp_path / "accounts.cae",
    )

    result = cli_main(["export", "--passphrase-file", str(missing_pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert calls == [
        ("select", "Select accounts to export"),
        ("path", str(Path.cwd() / "codex-auth-export.cae")),
    ]
    assert f"error: [Errno 2] No such file or directory: '{missing_pass_file}'" in captured.err


def test_cli_export_validates_passphrase_file_before_prompting(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    service = CodexAuthService()
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    missing_pass_file = tmp_path / "missing-pass.txt"

    prompt_calls: list[str] = []

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_saved_accounts",
        lambda accounts, message: prompt_calls.append("selection") or ["work"],
    )
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_export_path",
        lambda default_path: prompt_calls.append("path") or tmp_path / "accounts.cae",
    )

    result = cli_main(["export", "--passphrase-file", str(missing_pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert prompt_calls == ["selection", "path"]
    assert f"error: [Errno 2] No such file or directory: '{missing_pass_file}'" in captured.err


def test_cli_import_requires_interactive_terminal_even_with_passphrase_file(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source_home = tmp_path / "source-home"
    service = CodexAuthService(home=source_home)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    archive_path = tmp_path / "accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")
    service.write_export_archive(["work"], archive_path, passphrase="secret-pass")

    result = cli_main(["import", str(archive_path), "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "error: import requires an interactive terminal" in captured.err


def test_cli_import_reports_missing_archive_file_concisely(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    archive_path = tmp_path / "missing-accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)

    result = cli_main(["import", str(archive_path), "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert f"error: [Errno 2] No such file or directory: '{archive_path}'" in captured.err


def test_cli_import_reports_missing_archive_before_prompting_for_passphrase(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    archive_path = tmp_path / "missing-accounts.cae"

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_passphrase",
        lambda confirm: (_ for _ in ()).throw(AssertionError("passphrase prompt should not run")),
    )

    result = cli_main(["import", str(archive_path)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert f"error: [Errno 2] No such file or directory: '{archive_path}'" in captured.err


def test_cli_import_empty_selection_is_cancellation(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source_home = tmp_path / "source-home"
    source_service = CodexAuthService(home=source_home)
    source_service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    archive_path = tmp_path / "accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")
    source_service.write_export_archive(["work"], archive_path, passphrase="secret-pass")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr("codex_auth.prompts.prompt_select_archive_accounts", lambda accounts: [])

    result = cli_main(["import", str(archive_path), "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 3
    assert captured.out == ""
    assert "cancelled: import" in captured.err


def test_cli_import_with_empty_archive_is_an_error(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    archive_path = tmp_path / "empty-accounts.cae"
    archive_path.write_bytes(
        encrypt_transfer_archive(
            [],
            passphrase="secret-pass",
            exported_at="2026-04-05T10:00:00Z",
            tool_version="0.1.0",
        )
    )
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr(
        "codex_auth.prompts.prompt_select_archive_accounts",
        lambda accounts: (_ for _ in ()).throw(AssertionError("selection prompt should not run")),
    )

    result = cli_main(["import", str(archive_path), "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "error: No accounts available in import archive" in captured.err


def test_cli_import_expands_user_paths(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source_home = tmp_path / "source-home"
    source_service = CodexAuthService(home=source_home)
    source_service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    archive_path = tmp_path / "accounts.cae"
    source_service.write_export_archive(["work"], archive_path, passphrase="secret-pass")
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr("codex_auth.prompts.prompt_select_archive_accounts", lambda accounts: ["work"])
    monkeypatch.setattr(
        "codex_auth.prompts.build_import_plan",
        lambda archive_accounts, existing_accounts, selected_names: [
            ImportPlanItem(source_name="work", target_name="work", action="import"),
        ],
    )

    result = cli_main(["import", "~/accounts.cae", "--passphrase-file", "~/pass.txt"])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert "imported: work" in captured.out
    assert CodexAuthService().store.load_snapshot("work").account_id == "acct-work"


def test_cli_import_applies_selected_accounts(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source_home = tmp_path / "source-home"
    source_service = CodexAuthService(home=source_home)
    source_service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    source_service.store.save_snapshot("travel", make_snapshot("acct-travel"), force=False, mark_active=False)
    source_service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    archive_path = tmp_path / "accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")
    source_service.write_export_archive(["work", "travel", "personal"], archive_path, passphrase="secret-pass")

    target_service = CodexAuthService()
    target_service.store.save_snapshot("work", make_snapshot("acct-existing-work"), force=False, mark_active=True)
    live_before = make_snapshot("acct-live")
    target_service.store.write_live_auth(live_before)

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr("codex_auth.prompts.prompt_select_archive_accounts", lambda accounts: ["work", "travel", "personal"])
    monkeypatch.setattr(
        "codex_auth.prompts.build_import_plan",
        lambda archive_accounts, existing_accounts, selected_names: [
            ImportPlanItem(source_name="work", target_name="work", action="overwrite"),
            ImportPlanItem(source_name="travel", target_name="vacation", action="rename"),
            ImportPlanItem(source_name="personal", target_name="personal", action="skip"),
        ],
    )

    result = cli_main(["import", str(archive_path), "--passphrase-file", str(pass_file)])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert "imported: work, vacation" in captured.out
    assert "skipped: personal" in captured.out
    assert "overwritten: work" in captured.out
    assert "renamed: vacation" in captured.out
    assert target_service.store.load_snapshot("work").account_id == "acct-work"
    assert target_service.store.load_snapshot("vacation").account_id == "acct-travel"
    assert target_service.store.read_live_auth() == live_before
    assert target_service.store.current_active_name() == "work"
