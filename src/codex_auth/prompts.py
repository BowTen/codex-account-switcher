from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

from .errors import InteractiveRequiredError
from .models import AccountMetadata, ImportPlanItem, TransferAccount
from .validators import validate_account_name


def require_interactive(command_name: str, *, stdin: TextIO = sys.stdin) -> None:
    if not stdin.isatty():
        raise InteractiveRequiredError(f"{command_name} requires an interactive terminal")


def prompt_select_saved_accounts(accounts: list[AccountMetadata], message: str) -> list[str]:
    choices = [
        Choice(value=item.name, name=f"{item.name}  {item.auth_mode}  {item.account_id}")
        for item in accounts
    ]
    return inquirer.checkbox(
        message=message,
        choices=choices,
        instruction="Space to toggle, Enter to confirm",
    ).execute()


def prompt_select_archive_accounts(accounts: list[TransferAccount]) -> list[str]:
    choices = [
        Choice(value=item.name, name=f"{item.name}  {item.metadata.auth_mode}  {item.metadata.account_id}")
        for item in accounts
    ]
    return inquirer.checkbox(
        message="Select accounts to import",
        choices=choices,
        instruction="Space to toggle, Enter to confirm",
    ).execute()


def prompt_export_path(default_path: Path) -> Path:
    value = inquirer.text(message="Export file path", default=str(default_path)).execute().strip()
    return Path(value).expanduser()


def prompt_passphrase(*, confirm: bool) -> str:
    first = inquirer.secret(message="Passphrase").execute()
    if not confirm:
        return first
    second = inquirer.secret(message="Confirm passphrase").execute()
    if first != second:
        raise ValueError("Passphrases do not match")
    return first


def prompt_conflict_action(name: str) -> str:
    return inquirer.select(
        message=f"Account '{name}' already exists. Choose action",
        choices=["skip", "overwrite", "rename"],
    ).execute()


def prompt_new_account_name(source_name: str) -> str:
    return inquirer.text(message=f"Rename imported account '{source_name}' to").execute().strip()


def build_import_plan(
    archive_accounts: list[TransferAccount],
    existing_accounts: list[AccountMetadata],
    selected_names: set[str],
) -> list[ImportPlanItem]:
    existing_names = {item.name for item in existing_accounts}
    planned_targets: set[str] = set()
    plan: list[ImportPlanItem] = []

    for account in archive_accounts:
        if account.name not in selected_names:
            continue

        if account.name not in existing_names:
            if account.name in planned_targets:
                raise ValueError(f"Duplicate import target name: {account.name}")
            planned_targets.add(account.name)
            plan.append(ImportPlanItem(source_name=account.name, target_name=account.name, action="import"))
            continue

        action = prompt_conflict_action(account.name)
        if action == "skip":
            plan.append(ImportPlanItem(source_name=account.name, target_name=account.name, action="skip"))
            continue
        if action == "overwrite":
            if account.name in planned_targets:
                raise ValueError(f"Duplicate import target name: {account.name}")
            planned_targets.add(account.name)
            plan.append(ImportPlanItem(source_name=account.name, target_name=account.name, action="overwrite"))
            continue
        if action != "rename":
            raise ValueError(f"Invalid import action: {action}")

        new_name = validate_account_name(prompt_new_account_name(account.name))
        if new_name in existing_names or new_name in planned_targets:
            raise ValueError(f"Duplicate import target name: {new_name}")
        planned_targets.add(new_name)
        plan.append(ImportPlanItem(source_name=account.name, target_name=new_name, action="rename"))

    return plan
