import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


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
