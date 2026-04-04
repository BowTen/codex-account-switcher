import json
import os
import subprocess
import sys
from pathlib import Path

from codex_auth.cli import main as cli_main
from codex_auth.service import CodexAuthService


ROOT = Path(__file__).resolve().parents[1]


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(ROOT / "src")}
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


def test_cli_rename_remove_and_doctor(tmp_path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert run_cli(tmp_path, "save", "work").returncode == 0
    assert run_cli(tmp_path, "rename", "work", "primary").returncode == 0

    list_result = run_cli(tmp_path, "list")
    assert "primary" in list_result.stdout

    remove_result = run_cli(tmp_path, "rm", "primary", "--force-current", "--yes")
    assert remove_result.returncode == 0

    doctor_result = run_cli(tmp_path, "doctor")
    assert doctor_result.returncode == 0
    assert "codex_dir" in doctor_result.stdout


def test_cli_remove_command_path(tmp_path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert run_cli(tmp_path, "save", "work").returncode == 0
    assert run_cli(tmp_path, "remove", "work", "--force-current", "--yes").returncode == 0

    list_result = run_cli(tmp_path, "list")
    assert "work" not in list_result.stdout


def test_cli_remove_prompts_and_can_cancel_interactively(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert cli_main(["save", "work"]) == 0

    prompts: list[str] = []

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return "n"

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", fake_input)

    result = cli_main(["remove", "work", "--force-current"])

    assert result == 3
    assert prompts and "work" in prompts[0]
    assert (tmp_path / ".codex-account-switcher" / "accounts" / "work.json").exists()


def test_cli_remove_without_prompt_when_noninteractive(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert cli_main(["save", "work"]) == 0

    def fail_input(prompt: str = "") -> str:
        raise AssertionError(f"input() should not be called in non-interactive mode: {prompt}")

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", fail_input)

    result = cli_main(["remove", "work", "--force-current"])

    assert result == 0
    assert not (tmp_path / ".codex-account-switcher" / "accounts" / "work.json").exists()


def test_doctor_reports_corrupted_managed_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    assert cli_main(["save", "work"]) == 0
    snapshot_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    snapshot_path.write_text("{not valid json")

    service = CodexAuthService()
    result = service.doctor()

    assert result["managed_snapshots_valid"] == "false"
    assert result["registry_valid"] == "true"


def test_doctor_reports_malformed_registry_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(json.dumps(make_snapshot("acct-work")))

    registry_root = tmp_path / ".codex-account-switcher"
    registry_root.mkdir()
    (registry_root / "registry.json").write_text(json.dumps({"version": 1, "active_name": None}))

    service = CodexAuthService()
    result = service.doctor()

    assert result["registry_valid"] == "false"
    assert result["managed_snapshots_valid"] == "false"
