from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
from pathlib import Path

from . import prompts
from .errors import TransferError
from .models import UsageBatchAbortedEvent, UsageBatchCompletedEvent
from .service import CodexAuthService


CANCELLED_EXIT_CODE = 3
_PROMPT_CANCELLED = object()
_ALT_SCREEN_ENTER = "\x1b[?1049h"
_ALT_SCREEN_EXIT = "\x1b[?1049l"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"


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

    usage_parser = subparsers.add_parser("usage", help="Show usage limits for accounts.")
    usage_parser.add_argument("name", nargs="?")

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
    lines = content.splitlines()
    if not lines or not lines[0].strip():
        raise ValueError(f"Passphrase file must not be blank: {path}")
    if any(line.strip() for line in lines[1:]):
        raise ValueError(f"Passphrase file must contain a single non-empty line: {path}")
    return lines[0]


def run_prompt(command_name: str, prompt):
    try:
        return prompt()
    except KeyboardInterrupt:
        print(f"cancelled: {command_name}", file=sys.stderr)
        return _PROMPT_CANCELLED


def _format_percentage(value: float | int | None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _format_local_time(value: int | str | None) -> str:
    if value is None:
        return "unknown"

    dt: datetime | None = None
    if isinstance(value, int):
        dt = datetime.fromtimestamp(value, tz=timezone.utc).astimezone()
    elif isinstance(value, str):
        if value.isdigit():
            dt = datetime.fromtimestamp(int(value), tz=timezone.utc).astimezone()
        else:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
            except ValueError:
                return value
    if dt is None:
        return str(value)
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def _unicode_usage_bars_supported() -> bool:
    encoding = getattr(sys.stdout, "encoding", None)
    if not encoding:
        return False
    try:
        "█░".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _format_progress_bar(
    remaining_percent: float | int | None,
    width: int = 20,
    *,
    use_unicode: bool | None = None,
) -> str:
    if remaining_percent is None:
        return "[????????????????????]"
    if use_unicode is None:
        use_unicode = _unicode_usage_bars_supported()
    clamped = max(0, min(100, float(remaining_percent)))
    filled = int(round(clamped / 100 * width))
    filled = max(0, min(width, filled))
    filled_char = "█" if use_unicode else "#"
    empty_char = "░" if use_unicode else "-"
    return f"[{filled_char * filled}{empty_char * (width - filled)}]"


def _render_usage_window(label: str, window) -> list[str]:
    if window is None:
        return [f"{label}: no rate limit data"]

    remaining_percent = window.remaining_percent
    lines = [
        f"{label}: {_format_percentage(remaining_percent)}% remaining",
        f"  progress: {_format_progress_bar(remaining_percent)}",
        f"  reset (local): {_format_local_time(window.reset_at)}",
    ]
    return lines


def _render_usage_result(result) -> list[str]:
    lines = [f"account: {result.name}", f"state: {result.managed_state}", f"account_id: {result.account_id}"]
    if result.error is not None:
        lines.append(f"error: {result.error}")
        return lines

    if result.primary_window is None and result.secondary_window is None:
        lines.append("no rate limit data")
    else:
        lines.extend(_render_usage_window("5h limit", result.primary_window))
        lines.extend(_render_usage_window("Weekly limit", result.secondary_window))

    if result.credits_balance is not None or result.has_credits is not None or result.unlimited_credits is not None:
        credits_line = "credits:"
        credits_details: list[str] = []
        if result.credits_balance is not None:
            credits_details.append(str(result.credits_balance))
        if result.unlimited_credits is True:
            credits_details.append("unlimited")
        elif result.has_credits is True:
            credits_details.append("available")
        elif result.has_credits is False:
            credits_details.append("none")
        if credits_details:
            credits_line = f"{credits_line} {' '.join(credits_details)}"
        lines.append(credits_line)

    if result.refreshed:
        lines.append("refreshed: usage data updated during query")
    return lines


def _usage_sort_metric(value: float | int | None) -> float:
    if value is None:
        return float("inf")
    return float(value)


def _usage_success_sort_key(result) -> tuple[float, float, str]:
    primary_remaining = result.primary_window.remaining_percent if result.primary_window is not None else None
    secondary_remaining = result.secondary_window.remaining_percent if result.secondary_window is not None else None
    return (
        _usage_sort_metric(primary_remaining),
        _usage_sort_metric(secondary_remaining),
        result.name,
    )


def _order_usage_results(results) -> list:
    errored = [result for result in results if result.error is not None]
    successful = sorted((result for result in results if result.error is None), key=_usage_success_sort_key)
    return [*errored, *successful]


def _render_usage_results(results) -> tuple[list[str], bool]:
    lines: list[str] = []
    any_success = False
    for index, result in enumerate(_order_usage_results(results)):
        if index > 0:
            lines.append("")
        lines.extend(_render_usage_result(result))
        if result.error is None:
            any_success = True
    return lines, any_success


def _render_usage_status_area(
    *,
    phase: str,
    running_names: list[str],
    queued_names: list[str],
    error: str | None = None,
    timed_out_name: str | None = None,
) -> list[str]:
    lines = [
        f"phase: {phase}",
        f"running: {', '.join(running_names) if running_names else '-'}",
        f"queued: {', '.join(queued_names) if queued_names else '-'}",
    ]
    if timed_out_name is not None:
        lines.append(f"timed out: {timed_out_name}")
    if error is not None:
        lines.append(f"error: {error}")
    return lines


def _render_usage_live_lines(
    *,
    completed_results,
    phase: str,
    running_names: list[str],
    queued_names: list[str],
    error: str | None = None,
    timed_out_name: str | None = None,
) -> list[str]:
    lines: list[str] = []
    ordered_results = _order_usage_results(completed_results)
    for index, result in enumerate(ordered_results):
        if index > 0:
            lines.append("")
        lines.extend(_render_usage_result(result))
    if lines:
        lines.append("")
    lines.extend(
        _render_usage_status_area(
            phase=phase,
            running_names=running_names,
            queued_names=queued_names,
            error=error,
            timed_out_name=timed_out_name,
        )
    )
    return lines


def _stdout_is_tty() -> bool:
    isatty = getattr(sys.stdout, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _terminal_supports_ansi() -> bool:
    term = os.environ.get("TERM", "").strip().lower()
    return term not in {"", "dumb", "unknown"}


def _live_usage_enabled() -> bool:
    return _stdout_is_tty() and _terminal_supports_ansi()


def _draw_live_usage(lines: list[str]) -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    if lines:
        sys.stdout.write("\n".join(lines))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _enter_live_usage_screen() -> None:
    sys.stdout.write(f"{_ALT_SCREEN_ENTER}{_HIDE_CURSOR}")
    sys.stdout.flush()


def _exit_live_usage_screen() -> None:
    sys.stdout.write(f"{_SHOW_CURSOR}{_ALT_SCREEN_EXIT}")
    sys.stdout.flush()


def _write_usage_lines(lines: list[str]) -> None:
    if not lines:
        return
    sys.stdout.write("\n".join(lines))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _run_live_usage(service: CodexAuthService) -> int:
    completed_results: list = []
    phase = "starting"
    running_names: list[str] = []
    queued_names: list[str] = []
    aborted_error: str | None = None
    timed_out_name: str | None = None

    _enter_live_usage_screen()
    try:
        for event in service.stream_usage_accounts():
            phase = event.phase
            running_names = list(event.running_names)
            queued_names = list(event.queued_names)
            if isinstance(event, UsageBatchCompletedEvent):
                completed_results.append(event.result)
            if isinstance(event, UsageBatchAbortedEvent):
                aborted_error = event.error
                timed_out_name = event.timed_out_name

            _draw_live_usage(
                _render_usage_live_lines(
                    completed_results=completed_results,
                    phase=phase,
                    running_names=running_names,
                    queued_names=queued_names,
                    error=aborted_error,
                    timed_out_name=timed_out_name,
                )
            )

            if aborted_error is not None:
                break
    finally:
        _exit_live_usage_screen()

    if aborted_error is not None:
        _write_usage_lines(
            _render_usage_live_lines(
                completed_results=completed_results,
                phase=phase,
                running_names=running_names,
                queued_names=queued_names,
                error=aborted_error,
                timed_out_name=timed_out_name,
            )
        )
        return 1

    lines, any_success = _render_usage_results(completed_results)
    _write_usage_lines(lines)
    return 0 if any_success else 1


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

        if args.command == "usage":
            if args.name:
                result = service.get_usage_account(args.name)
                if result.error is not None:
                    raise ValueError(result.error)
                for line in _render_usage_result(result):
                    print(line)
                return 0 if result.error is None else 1

            if _live_usage_enabled():
                return _run_live_usage(service)

            results = service.list_usage_accounts()
            lines, any_success = _render_usage_results(results)
            for line in lines:
                print(line)
            return 0 if any_success else 1

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
            accounts = service.list_accounts()
            if not accounts:
                raise ValueError("No saved accounts available for export")
            selected_names = run_prompt(
                "export",
                lambda: prompts.prompt_select_saved_accounts(accounts, message="Select accounts to export"),
            )
            if selected_names is _PROMPT_CANCELLED:
                return CANCELLED_EXIT_CODE
            if not selected_names:
                print("cancelled: export", file=sys.stderr)
                return CANCELLED_EXIT_CODE
            output_path = run_prompt(
                "export",
                lambda: prompts.prompt_export_path(Path.cwd() / "codex-auth-export.cae"),
            )
            if output_path is _PROMPT_CANCELLED:
                return CANCELLED_EXIT_CODE
            passphrase = read_passphrase_from_file(args.passphrase_file) if args.passphrase_file else None
            if passphrase is None:
                passphrase = run_prompt("export", lambda: prompts.prompt_passphrase(confirm=True))
                if passphrase is _PROMPT_CANCELLED:
                    return CANCELLED_EXIT_CODE
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
                else run_prompt("import", lambda: prompts.prompt_passphrase(confirm=False))
            )
            if passphrase is _PROMPT_CANCELLED:
                return CANCELLED_EXIT_CODE
            archive = service.read_import_archive(archive_path, passphrase=passphrase)
            if not archive.accounts:
                raise ValueError("No accounts available in import archive")
            selected_names = run_prompt(
                "import",
                lambda: prompts.prompt_select_archive_accounts(archive.accounts),
            )
            if selected_names is _PROMPT_CANCELLED:
                return CANCELLED_EXIT_CODE
            if not selected_names:
                print("cancelled: import", file=sys.stderr)
                return CANCELLED_EXIT_CODE
            plan = run_prompt(
                "import",
                lambda: prompts.build_import_plan(archive.accounts, service.list_accounts(), set(selected_names)),
            )
            if plan is _PROMPT_CANCELLED:
                return CANCELLED_EXIT_CODE
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
