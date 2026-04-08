import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codex_auth import cli as cli_module
from codex_auth.cli import main as cli_main
from codex_auth.models import AccountUsageResult, UsageWindow


ROOT = Path(__file__).resolve().parents[1]


def write_fake_codex(bin_dir: Path) -> None:
    script = bin_dir / "codex"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "print('Logged in using ChatGPT')\n"
    )
    script.chmod(0o755)


def run_cli(home: Path, *args: str, path_prefix: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(ROOT / "src")}
    if path_prefix:
        env["PATH"] = f"{path_prefix}:{env['PATH']}"
    return subprocess.run(
        [sys.executable, "-m", "codex_auth", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def run_cli_with_pythonpath(
    home: Path,
    *args: str,
    pythonpath_entries: list[Path],
    path_prefix: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    env["PYTHONPATH"] = os.pathsep.join([str(path) for path in pythonpath_entries])
    if path_prefix:
        env["PATH"] = f"{path_prefix}:{env['PATH']}"
    return subprocess.run(
        [sys.executable, "-m", "codex_auth", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
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


def make_usage_window(*, used_percent: float | int | None, reset_at: int | str | None) -> UsageWindow:
    return UsageWindow(
        used_percent=used_percent,
        limit_window_seconds=18000,
        reset_at=reset_at,
        raw={},
    )


def make_usage_result(
    *,
    name: str,
    managed_state: str,
    account_id: str,
    primary_window: UsageWindow | None,
    secondary_window: UsageWindow | None,
    credits_balance: str | None = None,
    refreshed: bool = False,
    error: str | None = None,
) -> AccountUsageResult:
    return AccountUsageResult(
        name=name,
        managed_state=managed_state,
        account_id=account_id,
        plan_type="chatgpt",
        primary_window=primary_window,
        secondary_window=secondary_window,
        credits_balance=credits_balance,
        has_credits=credits_balance is not None,
        unlimited_credits=False if credits_balance is not None else None,
        refreshed=refreshed,
        refreshed_raw={"tokens": {}} if refreshed else None,
        error=error,
    )


class FakeStdout:
    def __init__(self, encoding: str | None) -> None:
        self.encoding = encoding


class FakeTextStream:
    def __init__(self, encoding: str | None) -> None:
        self.encoding = encoding
        self._chunks: list[str] = []

    def write(self, text: str) -> int:
        self._chunks.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def getvalue(self) -> str:
        return "".join(self._chunks)


def test_cli_save_list_current_and_inspect(tmp_path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert run_cli(tmp_path, "save", "work").returncode == 0

    list_result = run_cli(tmp_path, "ls")
    assert list_result.returncode == 0
    assert "work" in list_result.stdout

    current_result = run_cli(tmp_path, "current")
    assert current_result.returncode == 0
    assert "acct-work" in current_result.stdout

    inspect_result = run_cli(tmp_path, "inspect", "work")
    assert inspect_result.returncode == 0
    assert "chatgpt" in inspect_result.stdout


@pytest.mark.parametrize("command", ["list", "ls"])
def test_cli_list_commands_mark_active_account(tmp_path, command: str) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert run_cli(tmp_path, "save", "work").returncode == 0

    result = run_cli(tmp_path, command)
    assert result.returncode == 0
    assert "* work" in result.stdout


def test_cli_current_reports_unmanaged_live_auth_when_no_match(tmp_path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert run_cli(tmp_path, "save", "work").returncode == 0
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-personal")))

    result = run_cli(tmp_path, "current")
    assert result.returncode == 0
    assert "managed_state: unmanaged" in result.stdout
    assert "account_id: acct-personal" in result.stdout


def test_cli_reports_concise_error_without_traceback(tmp_path) -> None:
    result = run_cli(tmp_path, "inspect", "missing")

    assert result.returncode == 1
    assert "error: Unknown account: missing" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_usage_renders_mixed_managed_and_unmanaged_results(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_service = type(
        "FakeUsageService",
        (),
        {
            "list_usage_accounts": lambda self: [
                make_usage_result(
                    name="(live)",
                    managed_state="unmanaged",
                    account_id="acct-live",
                    primary_window=make_usage_window(used_percent=25, reset_at=1712224800),
                    secondary_window=make_usage_window(used_percent=60, reset_at="2026-04-08T18:00:00Z"),
                    credits_balance="12.5",
                    refreshed=True,
                ),
                make_usage_result(
                    name="work",
                    managed_state="managed",
                    account_id="acct-work",
                    primary_window=None,
                    secondary_window=None,
                ),
            ],
            "get_usage_account": lambda self, name: (_ for _ in ()).throw(AssertionError("unexpected get_usage_account")),
        },
    )()
    monkeypatch.setattr("codex_auth.cli.CodexAuthService", lambda: fake_service)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 0
    assert "account: (live)" in captured.out
    assert "state: unmanaged" in captured.out
    assert "5h limit" in captured.out
    assert "Weekly limit" in captured.out
    assert "credits: 12.5" in captured.out
    assert "refreshed" in captured.out
    assert "account: work" in captured.out
    assert "state: managed" in captured.out
    assert "no rate limit data" in captured.out
    assert captured.err == ""


def test_unicode_usage_bars_detection_uses_stdout_encoding_for_utf8(monkeypatch) -> None:
    monkeypatch.setattr(cli_module.sys, "stdout", FakeStdout("utf-8"))

    window = make_usage_window(used_percent=25, reset_at=1712224800)

    assert cli_module._unicode_usage_bars_supported() is True
    assert cli_module._render_usage_window("5h limit", window)[1] == "  progress: [███████████████░░░░░]"


def test_unicode_usage_bars_detection_falls_back_for_ascii_stdout(monkeypatch) -> None:
    monkeypatch.setattr(cli_module.sys, "stdout", FakeStdout("ascii"))

    window = make_usage_window(used_percent=25, reset_at=1712224800)

    assert cli_module._unicode_usage_bars_supported() is False
    assert cli_module._render_usage_window("5h limit", window)[1] == "  progress: [###############-----]"


def test_cli_usage_renders_unicode_progress_bars_when_stdout_supports_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = FakeTextStream("utf-8")
    stderr = FakeTextStream("utf-8")
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)
    monkeypatch.setattr(cli_module.sys, "stderr", stderr)

    class FakeUsageService:
        def list_usage_accounts(self) -> list[AccountUsageResult]:
            return [
                make_usage_result(
                    name="work",
                    managed_state="managed",
                    account_id="acct-work",
                    primary_window=make_usage_window(used_percent=25, reset_at=1712224800),
                    secondary_window=None,
                ),
            ]

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])

    assert result == 0
    assert "progress: [███████████████░░░░░]" in stdout.getvalue()
    assert "#" not in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_usage_falls_back_to_ascii_progress_bars_when_stdout_is_ascii(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = FakeTextStream("ascii")
    stderr = FakeTextStream("ascii")
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)
    monkeypatch.setattr(cli_module.sys, "stderr", stderr)

    class FakeUsageService:
        def list_usage_accounts(self) -> list[AccountUsageResult]:
            return [
                make_usage_result(
                    name="work",
                    managed_state="managed",
                    account_id="acct-work",
                    primary_window=make_usage_window(used_percent=25, reset_at=1712224800),
                    secondary_window=None,
                ),
            ]

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])

    assert result == 0
    assert "progress: [###############-----]" in stdout.getvalue()
    assert "█" not in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_usage_named_account_lookup_errors_are_concise(tmp_path) -> None:
    patch_dir = tmp_path / "patches"
    patch_dir.mkdir()
    (patch_dir / "sitecustomize.py").write_text(
        "from codex_auth import cli\n"
        "from codex_auth.models import AccountUsageResult\n"
        "\n"
        "class FakeUsageService:\n"
        "    def get_usage_account(self, name):\n"
        "        return AccountUsageResult(\n"
        "            name=name,\n"
        "            managed_state='managed',\n"
        "            account_id='acct-missing',\n"
        "            plan_type='chatgpt',\n"
        "            primary_window=None,\n"
        "            secondary_window=None,\n"
        "            credits_balance=None,\n"
        "            has_credits=None,\n"
        "            unlimited_credits=None,\n"
        "            refreshed=False,\n"
        "            refreshed_raw=None,\n"
        "            error='usage request failed: 404 Not Found',\n"
        "        )\n"
        "\n"
        "cli.CodexAuthService = FakeUsageService\n"
    )

    result = run_cli_with_pythonpath(
        tmp_path,
        "usage",
        "missing",
        pythonpath_entries=[patch_dir, ROOT / "src"],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "error: usage request failed: 404 Not Found" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_usage_batch_mixed_success_returns_zero_and_keeps_errors_visible(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeUsageService:
        def list_usage_accounts(self) -> list[AccountUsageResult]:
            return [
                make_usage_result(
                    name="work",
                    managed_state="managed",
                    account_id="acct-work",
                    primary_window=make_usage_window(used_percent=10, reset_at=1712224800),
                    secondary_window=make_usage_window(used_percent=20, reset_at=1712228400),
                ),
                make_usage_result(
                    name="travel",
                    managed_state="managed",
                    account_id="acct-travel",
                    primary_window=None,
                    secondary_window=None,
                    error="usage request failed: 429 Too Many Requests",
                ),
            ]

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 0
    assert "5h limit: 90% remaining" in captured.out
    assert "account: travel" in captured.out
    assert "error: usage request failed: 429 Too Many Requests" in captured.out
    assert captured.err == ""


def test_cli_usage_reports_preflight_network_failure(tmp_path, monkeypatch, capsys) -> None:
    from codex_auth.errors import UsageNetworkError

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeUsageService:
        def list_usage_accounts(self):
            raise UsageNetworkError("usage endpoint unreachable: network is unreachable")

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: usage endpoint unreachable: network is unreachable\n"
    assert "Traceback" not in captured.err


def test_cli_usage_reports_timeout_failure(tmp_path, monkeypatch, capsys) -> None:
    from codex_auth.errors import UsageTimeoutError

    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeUsageService:
        def list_usage_accounts(self):
            raise UsageTimeoutError("usage request timed out")

    monkeypatch.setattr("codex_auth.cli.CodexAuthService", FakeUsageService)

    result = cli_main(["usage"])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: usage request timed out\n"
    assert "Traceback" not in captured.err


def test_cli_use_switches_to_a_saved_account(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir)

    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert run_cli(tmp_path, "save", "work").returncode == 0
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-personal")))
    assert run_cli(tmp_path, "save", "personal").returncode == 0

    result = run_cli(tmp_path, "use", "work", path_prefix=str(bin_dir))
    assert result.returncode == 0
    assert "switched: work" in result.stdout
    assert "Logged in using ChatGPT" in result.stdout
