from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import prompts
from .errors import TransferError
from .service import CodexAuthService


CANCELLED_EXIT_CODE = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-auth",
        description="Manage local Codex auth.json account snapshots.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    save_parser = subparsers.add_parser("save", help="Save the current live auth.json as a named account.")
    save_parser.add_argument("name")
    save_parser.add_argument("--force", action="store_true")

    use_parser = subparsers.add_parser("use", help="Switch to a saved account.")
    use_parser.add_argument("name")

    subparsers.add_parser("list", help="List saved accounts.")
    subparsers.add_parser("ls", help="List saved accounts.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a saved account.")
    inspect_parser.add_argument("name")

    subparsers.add_parser("current", help="Show the current live account summary.")

    rename_parser = subparsers.add_parser("rename", help="Rename a saved account.")
    rename_parser.add_argument("old")
    rename_parser.add_argument("new")
    rename_parser.add_argument("--force", action="store_true")

    remove_parser = subparsers.add_parser("remove", help="Remove a saved account.")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--yes", action="store_true")
    remove_parser.add_argument("--force-current", action="store_true")

    rm_parser = subparsers.add_parser("rm", help="Remove a saved account.")
    rm_parser.add_argument("name")
    rm_parser.add_argument("--yes", action="store_true")
    rm_parser.add_argument("--force-current", action="store_true")

    export_parser = subparsers.add_parser("export", help="Export saved accounts into an encrypted transfer file.")
    export_parser.add_argument("--passphrase-file")

    import_parser = subparsers.add_parser("import", help="Import saved accounts from an encrypted transfer file.")
    import_parser.add_argument("file")
    import_parser.add_argument("--passphrase-file")

    subparsers.add_parser("doctor", help="Inspect local Codex and store state.")
    return parser


def print_kv_map(payload: dict[str, str | None]) -> None:
    for key, value in payload.items():
        print(f"{key}: {value}")


def print_name_list(label: str, names: list[str]) -> None:
    rendered = ", ".join(names) if names else "-"
    print(f"{label}: {rendered}")


def confirm_removal(name: str) -> bool:
    try:
        response = input(f"Remove account '{name}'? [y/N] ").strip().lower()
    except EOFError:
        return False
    return response in {"y", "yes"}


def resolve_cli_path(path: str) -> Path:
    return Path(path).expanduser()


def read_passphrase_from_file(path: str) -> str:
    content = resolve_cli_path(path).read_text()
    if content.endswith("\r\n"):
        content = content[:-2]
    elif content.endswith("\n") or content.endswith("\r"):
        content = content[:-1]
    if content == "":
        raise ValueError(f"Passphrase file is empty: {path}")
    return content


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = CodexAuthService()

    try:
        if args.command == "save":
            metadata = service.save_current(args.name, force=args.force)
            print(f"saved: {metadata.name} ({metadata.account_id})")
            return 0

        if args.command == "use":
            result = service.use_account(args.name)
            print(f"switched: {result.account_name}")
            output = result.verification.stdout.strip()
            if output:
                print(output)
            return 0 if result.verified else 2

        if args.command in {"list", "ls"}:
            active_name = service.active_account_name()
            for item in service.list_accounts():
                marker = "*" if item.name == active_name else " "
                print(f"{marker} {item.name}\t{item.auth_mode}\t{item.account_id}\t{item.updated_at}")
            return 0

        if args.command == "inspect":
            print_kv_map(service.inspect_account(args.name))
            return 0

        if args.command == "current":
            print_kv_map(service.current_account())
            return 0

        if args.command == "rename":
            service.rename_account(args.old, args.new, force=args.force)
            print(f"renamed: {args.old} -> {args.new}")
            return 0

        if args.command in {"remove", "rm"}:
            if not args.yes and sys.stdin.isatty() and not confirm_removal(args.name):
                print(f"cancelled: remove {args.name}", file=sys.stderr)
                return CANCELLED_EXIT_CODE
            service.remove_account(args.name, force_current=args.force_current)
            print(f"removed: {args.name}")
            return 0

        if args.command == "export":
            prompts.require_interactive("export")
            passphrase = read_passphrase_from_file(args.passphrase_file) if args.passphrase_file else None
            accounts = service.list_accounts()
            if not accounts:
                raise ValueError("No saved accounts available for export")
            selected_names = prompts.prompt_select_saved_accounts(accounts, message="Select accounts to export")
            if not selected_names:
                print("cancelled: export", file=sys.stderr)
                return CANCELLED_EXIT_CODE
            output_path = prompts.prompt_export_path(Path.cwd() / "codex-auth-export.cae")
            if passphrase is None:
                passphrase = prompts.prompt_passphrase(confirm=True)
            service.write_export_archive(selected_names, output_path, passphrase=passphrase)
            print(f"exported: {len(selected_names)} accounts -> {output_path}")
            return 0

        if args.command == "import":
            prompts.require_interactive("import")
            archive_path = resolve_cli_path(args.file)
            archive_path.read_bytes()
            passphrase = (
                read_passphrase_from_file(args.passphrase_file)
                if args.passphrase_file
                else prompts.prompt_passphrase(confirm=False)
            )
            archive = service.read_import_archive(archive_path, passphrase=passphrase)
            if not archive.accounts:
                raise ValueError("No accounts available in import archive")
            selected_names = prompts.prompt_select_archive_accounts(archive.accounts)
            if not selected_names:
                print("cancelled: import", file=sys.stderr)
                return CANCELLED_EXIT_CODE
            plan = prompts.build_import_plan(archive.accounts, service.list_accounts(), set(selected_names))
            result = service.apply_import_archive(archive, plan)
            print_name_list("imported", result.imported)
            print_name_list("skipped", result.skipped)
            print_name_list("overwritten", result.overwritten)
            print_name_list("renamed", result.renamed)
            return 0

        if args.command == "doctor":
            print_kv_map(service.doctor())
            return 0
    except (OSError, ValueError, TransferError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 1
