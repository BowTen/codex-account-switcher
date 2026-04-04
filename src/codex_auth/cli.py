from __future__ import annotations

import argparse

from .service import CodexAuthService


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
    return parser


def print_kv_map(payload: dict[str, str | None]) -> None:
    for key, value in payload.items():
        print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = CodexAuthService()

    if args.command == "save":
        metadata = service.save_current(args.name, force=args.force)
        print(f"saved: {metadata.name} ({metadata.account_id})")
        return 0

    if args.command == "use":
        result = service.use_account(args.name)
        print(f"switched: {result.account_name}")
        print(result.verification.stdout.strip())
        return 0 if result.verified else 2

    if args.command in {"list", "ls"}:
        active_name = service.store.matched_active_name()
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

    parser.error(f"Unhandled command: {args.command}")
    return 0
