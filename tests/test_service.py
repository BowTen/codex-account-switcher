import os
from pathlib import Path

from codex_auth.service import CodexAuthService


def write_fake_codex(bin_dir: Path, *, returncode: int = 0, output: str = "Logged in using ChatGPT\n") -> None:
    script = bin_dir / "codex"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"print({output!r}, end='')\n"
        f"raise SystemExit({returncode})\n"
    )
    script.chmod(0o755)


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


def test_use_account_switches_live_auth_and_marks_verified(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir)

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    service = CodexAuthService(home=tmp_path, env=env)

    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-work"))

    result = service.use_account("personal")

    assert result.switched is True
    assert result.verified is True
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-personal"
    assert service.store.current_active_name() == "personal"


def test_use_account_reports_partial_success_when_verification_fails(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_codex(bin_dir, returncode=1, output="Not logged in\n")

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    service = CodexAuthService(home=tmp_path, env=env)

    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    service.store.write_live_auth(make_snapshot("acct-work"))

    result = service.use_account("personal")

    assert result.switched is True
    assert result.verified is False
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-personal"
    assert service.store.current_active_name() == "work"
