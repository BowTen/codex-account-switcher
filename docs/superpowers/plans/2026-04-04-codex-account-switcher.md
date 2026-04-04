# Codex Account Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI named `codex-auth` that stores multiple local Codex `auth.json` snapshots, switches the active account by replacing `~/.codex/auth.json`, and validates the switch with `codex login status`.

**Architecture:** Use a stdlib-first Python package under `src/codex_auth` with a thin argparse CLI, focused validation and store modules, and a service layer that coordinates save, switch, inspection, and diagnostics. Keep all secrets in local snapshot files under `~/.codex-account-switcher`, store only non-sensitive metadata in `registry.json`, and use atomic file replacement for the live `~/.codex/auth.json`.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `argparse`, `pathlib`, `json`, `subprocess`, GitHub Actions

---

## File Structure

- Create: `.gitignore`
  Ignore local virtualenvs, caches, build output, and secret fixtures.
- Create: `.python-version`
  Pin the local interpreter version for `uv`.
- Create: `pyproject.toml`
  Define package metadata, console entrypoint, build backend, and pytest config.
- Create: `README.md`
  Document install, command usage, safety model, and release workflow.
- Create: `src/codex_auth/__init__.py`
  Expose the package version.
- Create: `src/codex_auth/__main__.py`
  Support `python -m codex_auth`.
- Create: `src/codex_auth/cli.py`
  Build the parser, map subcommands to service calls, and format output.
- Create: `src/codex_auth/models.py`
  Hold typed dataclasses for snapshots, metadata, verification, and diagnostics.
- Create: `src/codex_auth/validators.py`
  Validate account names and parse supported `auth.json` snapshots.
- Create: `src/codex_auth/store.py`
  Read and write registry and snapshot files, enforce permissions, and update active state.
- Create: `src/codex_auth/codex_cli.py`
  Wrap `codex login status`.
- Create: `src/codex_auth/service.py`
  Orchestrate save, use, list, inspect, rename, remove, and doctor flows.
- Create: `tests/test_cli_smoke.py`
  Verify the package module starts and prints help.
- Create: `tests/test_validators.py`
  Verify name validation and snapshot parsing.
- Create: `tests/test_store.py`
  Verify snapshot storage, registry updates, active tracking, and safety checks.
- Create: `tests/test_service.py`
  Verify save and switch workflows, including verification success and failure.
- Create: `tests/test_cli_read_commands.py`
  Verify user-facing CLI flows for `save`, `list`, `ls`, `inspect`, `current`, and `use`.
- Create: `tests/test_cli_admin_commands.py`
  Verify `rename`, `remove`, `rm`, and `doctor`.
- Create: `tests/test_project_files.py`
  Verify the repo contains the release docs and CI workflow promised by the README.
- Create: `.github/workflows/ci.yml`
  Run tests on pushes and pull requests.

### Task 1: Bootstrap The Package And CLI Smoke Test

**Files:**
- Create: `.gitignore`
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `src/codex_auth/__init__.py`
- Create: `src/codex_auth/__main__.py`
- Create: `src/codex_auth/cli.py`
- Test: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/test_cli_smoke.py
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_module_help_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codex_auth", "--help"],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "codex-auth" in result.stdout
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: FAIL with `No module named codex_auth`

- [ ] **Step 3: Write the minimal package skeleton**

```text
# .python-version
3.12
```

```gitignore
# .gitignore
.venv/
.pytest_cache/
.mypy_cache/
__pycache__/
*.pyc
dist/
build/
*.egg-info/
```

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "codex-account-switcher"
version = "0.1.0"
description = "Manage multiple local Codex auth.json snapshots"
readme = "README.md"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
codex-auth = "codex_auth.cli:main"

[dependency-groups]
dev = ["pytest>=8.3,<9"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

```python
# src/codex_auth/__init__.py
__all__ = ["__version__"]

__version__ = "0.1.0"
```

```python
# src/codex_auth/__main__.py
from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# src/codex_auth/cli.py
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-auth",
        description="Manage local Codex auth.json account snapshots.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit the bootstrap**

```bash
git add .gitignore .python-version pyproject.toml src/codex_auth/__init__.py src/codex_auth/__main__.py src/codex_auth/cli.py tests/test_cli_smoke.py
git commit -m "chore: bootstrap codex account switcher package"
```

### Task 2: Add Snapshot And Name Validation

**Files:**
- Create: `src/codex_auth/models.py`
- Create: `src/codex_auth/validators.py`
- Test: `tests/test_validators.py`

- [ ] **Step 1: Write the failing validation tests**

```python
# tests/test_validators.py
import pytest

from codex_auth.validators import parse_snapshot, validate_account_name


def test_parse_snapshot_extracts_required_metadata() -> None:
    raw = {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
            "account_id": "acct-123",
        },
    }

    snapshot = parse_snapshot(raw)

    assert snapshot.auth_mode == "chatgpt"
    assert snapshot.account_id == "acct-123"
    assert snapshot.last_refresh == "2026-04-04T10:00:00Z"


def test_validate_account_name_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="Invalid account name"):
        validate_account_name("work account")
```

- [ ] **Step 2: Run the validation tests to verify they fail**

Run: `uv run pytest tests/test_validators.py -v`
Expected: FAIL with `cannot import name 'parse_snapshot'`

- [ ] **Step 3: Write the validation models and parser**

```python
# src/codex_auth/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AccountSnapshot:
    auth_mode: str
    account_id: str
    last_refresh: str | None
    raw: dict[str, Any]


@dataclass(slots=True)
class AccountMetadata:
    name: str
    auth_mode: str
    account_id: str
    created_at: str
    updated_at: str
    last_refresh: str | None
    last_verified_at: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "auth_mode": self.auth_mode,
            "account_id": self.account_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_refresh": self.last_refresh,
            "last_verified_at": self.last_verified_at,
        }
```

```python
# src/codex_auth/validators.py
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .models import AccountMetadata, AccountSnapshot


NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def utc_now_iso() -> str:
    value = datetime.now(UTC).replace(microsecond=0).isoformat()
    return value.replace("+00:00", "Z")


def validate_account_name(name: str) -> str:
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid account name: {name!r}")
    return name


def parse_snapshot(raw: dict[str, Any]) -> AccountSnapshot:
    auth_mode = raw.get("auth_mode")
    tokens = raw.get("tokens")
    if not isinstance(auth_mode, str):
        raise ValueError("Missing or invalid auth_mode")
    if not isinstance(tokens, dict):
        raise ValueError("Missing or invalid tokens")

    required = ("access_token", "refresh_token", "id_token", "account_id")
    missing = [key for key in required if not isinstance(tokens.get(key), str)]
    if missing:
        raise ValueError(f"Missing required token fields: {', '.join(missing)}")

    return AccountSnapshot(
        auth_mode=auth_mode,
        account_id=tokens["account_id"],
        last_refresh=raw.get("last_refresh"),
        raw=raw,
    )


def build_metadata(
    name: str,
    snapshot: AccountSnapshot,
    *,
    created_at: str | None = None,
    last_verified_at: str | None = None,
) -> AccountMetadata:
    now = utc_now_iso()
    return AccountMetadata(
        name=validate_account_name(name),
        auth_mode=snapshot.auth_mode,
        account_id=snapshot.account_id,
        created_at=created_at or now,
        updated_at=now,
        last_refresh=snapshot.last_refresh,
        last_verified_at=last_verified_at,
    )
```

- [ ] **Step 4: Run the validation tests to verify they pass**

Run: `uv run pytest tests/test_validators.py -v`
Expected: PASS

- [ ] **Step 5: Commit the validation layer**

```bash
git add src/codex_auth/models.py src/codex_auth/validators.py tests/test_validators.py
git commit -m "feat: validate auth snapshots and account names"
```

### Task 3: Implement The Snapshot Store And Registry

**Files:**
- Create: `src/codex_auth/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing store tests**

```python
# tests/test_store.py
import json

import pytest

from codex_auth.store import AccountStore


def make_snapshot(account_id: str) -> dict[str, object]:
    return {
        "auth_mode": "chatgpt",
        "last_refresh": "2026-04-04T10:00:00Z",
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id",
            "account_id": account_id,
        },
    }


def test_save_snapshot_writes_account_file_and_registry(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    snapshot_path = tmp_path / ".codex-account-switcher" / "accounts" / "work.json"
    registry_path = tmp_path / ".codex-account-switcher" / "registry.json"

    assert snapshot_path.exists()
    registry = json.loads(registry_path.read_text())
    assert registry["active_name"] == "work"
    assert registry["accounts"]["work"]["account_id"] == "acct-work"


def test_remove_active_snapshot_requires_force_current(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)

    with pytest.raises(ValueError, match="currently active"):
        store.remove_snapshot("work", force_current=False)


def test_matched_active_name_returns_none_when_live_auth_has_drifted(tmp_path) -> None:
    store = AccountStore(tmp_path)
    store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    store.write_live_auth(make_snapshot("acct-other"))

    assert store.matched_active_name() is None
```

- [ ] **Step 2: Run the store tests to verify they fail**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL with `No module named 'codex_auth.store'`

- [ ] **Step 3: Write the local store implementation**

```python
# src/codex_auth/store.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import AccountMetadata, AccountSnapshot
from .validators import build_metadata, parse_snapshot, validate_account_name


class AccountStore:
    def __init__(self, home: Path | str | None = None) -> None:
        self.home = Path(home).expanduser() if home is not None else Path.home()
        self.codex_dir = self.home / ".codex"
        self.root = self.home / ".codex-account-switcher"
        self.accounts_dir = self.root / "accounts"
        self.registry_path = self.root / "registry.json"
        self.live_auth_path = self.codex_dir / "auth.json"

    def ensure_dirs(self) -> None:
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self.codex_dir.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "active_name": None, "accounts": {}}
        return json.loads(self.registry_path.read_text())

    def save_registry(self, registry: dict[str, Any]) -> None:
        self.ensure_dirs()
        self._write_json_atomic(self.registry_path, registry)

    def load_snapshot(self, name: str) -> AccountSnapshot:
        validate_account_name(name)
        path = self.accounts_dir / f"{name}.json"
        if not path.exists():
            raise ValueError(f"Unknown account: {name}")
        return parse_snapshot(json.loads(path.read_text()))

    def save_snapshot(
        self,
        name: str,
        raw: dict[str, Any],
        *,
        force: bool,
        mark_active: bool,
    ) -> AccountMetadata:
        name = validate_account_name(name)
        self.ensure_dirs()
        path = self.accounts_dir / f"{name}.json"
        if path.exists() and not force:
            raise ValueError(f"Account already exists: {name}")

        snapshot = parse_snapshot(raw)
        registry = self.load_registry()
        existing = registry["accounts"].get(name)
        created_at = existing["created_at"] if existing else None
        last_verified_at = existing["last_verified_at"] if existing else None
        metadata = build_metadata(
            name,
            snapshot,
            created_at=created_at,
            last_verified_at=last_verified_at,
        )

        self._write_json_atomic(path, raw)
        registry["accounts"][name] = metadata.to_dict()
        if mark_active:
            registry["active_name"] = name
        self.save_registry(registry)
        return metadata

    def list_metadata(self) -> list[AccountMetadata]:
        registry = self.load_registry()
        accounts = registry["accounts"].values()
        return [AccountMetadata(**item) for item in sorted(accounts, key=lambda item: item["name"])]

    def current_active_name(self) -> str | None:
        return self.load_registry()["active_name"]

    def matched_active_name(self) -> str | None:
        active_name = self.current_active_name()
        if not active_name:
            return None

        live = self.read_live_auth()
        if live is None:
            return None

        live_snapshot = parse_snapshot(live)
        registry = self.load_registry()
        entry = registry["accounts"].get(active_name)
        if entry is None:
            return None

        if entry["auth_mode"] != live_snapshot.auth_mode:
            return None
        if entry["account_id"] != live_snapshot.account_id:
            return None
        return active_name

    def remove_snapshot(self, name: str, *, force_current: bool) -> None:
        registry = self.load_registry()
        if name not in registry["accounts"]:
            raise ValueError(f"Unknown account: {name}")
        if registry["active_name"] == name and not force_current:
            raise ValueError("Refusing to remove the currently active account without --force-current")

        path = self.accounts_dir / f"{name}.json"
        if path.exists():
            path.unlink()
        registry["accounts"].pop(name)
        if registry["active_name"] == name:
            registry["active_name"] = None
        self.save_registry(registry)

    def rename_snapshot(self, old: str, new: str, *, force: bool) -> None:
        old = validate_account_name(old)
        new = validate_account_name(new)
        registry = self.load_registry()
        if old not in registry["accounts"]:
            raise ValueError(f"Unknown account: {old}")
        if new in registry["accounts"] and not force:
            raise ValueError(f"Account already exists: {new}")

        old_path = self.accounts_dir / f"{old}.json"
        new_path = self.accounts_dir / f"{new}.json"
        self.ensure_dirs()
        old_path.replace(new_path)

        entry = registry["accounts"].pop(old)
        entry["name"] = new
        registry["accounts"][new] = entry
        if registry["active_name"] == old:
            registry["active_name"] = new
        self.save_registry(registry)

    def read_live_auth(self) -> dict[str, Any] | None:
        if not self.live_auth_path.exists():
            return None
        return json.loads(self.live_auth_path.read_text())

    def write_live_auth(self, raw: dict[str, Any]) -> None:
        self.ensure_dirs()
        self._write_json_atomic(self.live_auth_path, raw)

    def mark_verified(self, name: str, verified_at: str) -> None:
        registry = self.load_registry()
        entry = registry["accounts"][name]
        entry["last_verified_at"] = verified_at
        registry["active_name"] = name
        self.save_registry(registry)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)
```

- [ ] **Step 4: Run the store tests to verify they pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit the store layer**

```bash
git add src/codex_auth/store.py tests/test_store.py
git commit -m "feat: add local snapshot store and registry"
```

### Task 4: Add Save And Switch Services With Codex Verification

**Files:**
- Create: `src/codex_auth/codex_cli.py`
- Create: `src/codex_auth/service.py`
- Modify: `src/codex_auth/models.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
# tests/test_service.py
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
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `uv run pytest tests/test_service.py -v`
Expected: FAIL with `No module named 'codex_auth.service'`

- [ ] **Step 3: Write the service layer and Codex wrapper**

```python
# src/codex_auth/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AccountSnapshot:
    auth_mode: str
    account_id: str
    last_refresh: str | None
    raw: dict[str, Any]


@dataclass(slots=True)
class AccountMetadata:
    name: str
    auth_mode: str
    account_id: str
    created_at: str
    updated_at: str
    last_refresh: str | None
    last_verified_at: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "auth_mode": self.auth_mode,
            "account_id": self.account_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_refresh": self.last_refresh,
            "last_verified_at": self.last_verified_at,
        }


@dataclass(slots=True)
class VerificationResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class UseResult:
    switched: bool
    verified: bool
    account_name: str
    verification: VerificationResult
```

```python
# src/codex_auth/codex_cli.py
from __future__ import annotations

import shutil
import subprocess
from typing import Mapping

from .models import VerificationResult


def run_login_status(
    executable: str = "codex",
    *,
    env: Mapping[str, str] | None = None,
) -> VerificationResult:
    if shutil.which(executable, path=env.get("PATH") if env else None) is None:
        raise FileNotFoundError(f"Could not find executable: {executable}")

    result = subprocess.run(
        [executable, "login", "status"],
        capture_output=True,
        text=True,
        env=dict(env) if env else None,
    )
    return VerificationResult(
        ok=result.returncode == 0,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
```

```python
# src/codex_auth/service.py
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping

from .codex_cli import run_login_status
from .models import AccountMetadata, UseResult
from .store import AccountStore
from .validators import utc_now_iso, validate_account_name


class CodexAuthService:
    def __init__(
        self,
        *,
        home: Path | str | None = None,
        codex_executable: str = "codex",
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.store = AccountStore(home)
        self.codex_executable = codex_executable
        self.env = env

    def save_current(self, name: str, *, force: bool) -> AccountMetadata:
        validate_account_name(name)
        raw = self.store.read_live_auth()
        if raw is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        return self.store.save_snapshot(name, raw, force=force, mark_active=True)

    def use_account(self, name: str) -> UseResult:
        validate_account_name(name)
        current_name = self.store.matched_active_name()
        current_live = self.store.read_live_auth()
        if current_name and current_live is not None:
            self.store.save_snapshot(current_name, current_live, force=True, mark_active=True)

        target = self.store.load_snapshot(name)
        self.store.write_live_auth(target.raw)

        verification = run_login_status(self.codex_executable, env=self.env)
        if verification.ok:
            self.store.mark_verified(name, utc_now_iso())

        return UseResult(
            switched=True,
            verified=verification.ok,
            account_name=name,
            verification=verification,
        )
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `uv run pytest tests/test_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit the save and switch service**

```bash
git add src/codex_auth/models.py src/codex_auth/codex_cli.py src/codex_auth/service.py tests/test_service.py
git commit -m "feat: add save and switch workflows"
```

### Task 5: Expose Save, List, Inspect, Current, Use, And `ls` In The CLI

**Files:**
- Modify: `src/codex_auth/service.py`
- Modify: `src/codex_auth/cli.py`
- Test: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Write the failing read-command CLI tests**

```python
# tests/test_cli_read_commands.py
import json
import os
import subprocess
import sys
from pathlib import Path


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
```

- [ ] **Step 2: Run the CLI read-command tests to verify they fail**

Run: `uv run pytest tests/test_cli_read_commands.py -v`
Expected: FAIL because the CLI does not recognize `save`, `ls`, `current`, or `inspect`

- [ ] **Step 3: Implement the read command surface**

```python
# src/codex_auth/service.py
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .codex_cli import run_login_status
from .models import AccountMetadata, UseResult
from .store import AccountStore
from .validators import parse_snapshot, utc_now_iso, validate_account_name


class CodexAuthService:
    def __init__(
        self,
        *,
        home: Path | str | None = None,
        codex_executable: str = "codex",
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.store = AccountStore(home)
        self.codex_executable = codex_executable
        self.env = env

    def save_current(self, name: str, *, force: bool) -> AccountMetadata:
        validate_account_name(name)
        raw = self.store.read_live_auth()
        if raw is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        return self.store.save_snapshot(name, raw, force=force, mark_active=True)

    def use_account(self, name: str) -> UseResult:
        validate_account_name(name)
        current_name = self.store.matched_active_name()
        current_live = self.store.read_live_auth()
        if current_name and current_live is not None:
            self.store.save_snapshot(current_name, current_live, force=True, mark_active=True)

        target = self.store.load_snapshot(name)
        self.store.write_live_auth(target.raw)

        verification = run_login_status(self.codex_executable, env=self.env)
        if verification.ok:
            self.store.mark_verified(name, utc_now_iso())

        return UseResult(
            switched=True,
            verified=verification.ok,
            account_name=name,
            verification=verification,
        )

    def list_accounts(self) -> list[AccountMetadata]:
        return self.store.list_metadata()

    def inspect_account(self, name: str) -> dict[str, str | None]:
        registry = self.store.load_registry()
        if name not in registry["accounts"]:
            raise ValueError(f"Unknown account: {name}")
        entry = registry["accounts"][name]
        return {
            "name": entry["name"],
            "managed_state": "managed",
            "auth_mode": entry["auth_mode"],
            "account_id": entry["account_id"],
            "created_at": entry["created_at"],
            "updated_at": entry["updated_at"],
            "last_refresh": entry["last_refresh"],
            "last_verified_at": entry["last_verified_at"],
        }

    def current_account(self) -> dict[str, str | None]:
        active_name = self.store.matched_active_name()
        live = self.store.read_live_auth()
        if active_name:
            return self.inspect_account(active_name)
        if live is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        snapshot = parse_snapshot(live)
        return {
            "name": None,
            "managed_state": "unmanaged",
            "auth_mode": snapshot.auth_mode,
            "account_id": snapshot.account_id,
            "created_at": None,
            "updated_at": None,
            "last_refresh": snapshot.last_refresh,
            "last_verified_at": None,
        }
```

```python
# src/codex_auth/cli.py
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
    return 1
```

- [ ] **Step 4: Run the CLI read-command tests to verify they pass**

Run: `uv run pytest tests/test_cli_read_commands.py -v`
Expected: PASS

- [ ] **Step 5: Commit the read commands**

```bash
git add src/codex_auth/service.py src/codex_auth/cli.py tests/test_cli_read_commands.py
git commit -m "feat: add read-focused cli commands"
```

### Task 6: Add `rename`, `remove`, `rm`, And `doctor`

**Files:**
- Modify: `src/codex_auth/service.py`
- Modify: `src/codex_auth/cli.py`
- Test: `tests/test_cli_admin_commands.py`

- [ ] **Step 1: Write the failing admin-command CLI tests**

```python
# tests/test_cli_admin_commands.py
import json
import os
import subprocess
import sys
from pathlib import Path


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

    remove_result = run_cli(tmp_path, "rm", "primary", "--force-current")
    assert remove_result.returncode == 0

    doctor_result = run_cli(tmp_path, "doctor")
    assert doctor_result.returncode == 0
    assert "codex_dir" in doctor_result.stdout
```

- [ ] **Step 2: Run the admin-command CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli_admin_commands.py -v`
Expected: FAIL because the CLI does not recognize `rename`, `rm`, or `doctor`

- [ ] **Step 3: Implement the administrative commands**

```python
# src/codex_auth/service.py
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .codex_cli import run_login_status
from .models import AccountMetadata, UseResult
from .store import AccountStore
from .validators import parse_snapshot, utc_now_iso, validate_account_name


class CodexAuthService:
    def __init__(
        self,
        *,
        home: Path | str | None = None,
        codex_executable: str = "codex",
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.store = AccountStore(home)
        self.codex_executable = codex_executable
        self.env = env

    def save_current(self, name: str, *, force: bool) -> AccountMetadata:
        validate_account_name(name)
        raw = self.store.read_live_auth()
        if raw is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        return self.store.save_snapshot(name, raw, force=force, mark_active=True)

    def use_account(self, name: str) -> UseResult:
        validate_account_name(name)
        current_name = self.store.matched_active_name()
        current_live = self.store.read_live_auth()
        if current_name and current_live is not None:
            self.store.save_snapshot(current_name, current_live, force=True, mark_active=True)

        target = self.store.load_snapshot(name)
        self.store.write_live_auth(target.raw)
        verification = run_login_status(self.codex_executable, env=self.env)
        if verification.ok:
            self.store.mark_verified(name, utc_now_iso())

        return UseResult(
            switched=True,
            verified=verification.ok,
            account_name=name,
            verification=verification,
        )

    def list_accounts(self) -> list[AccountMetadata]:
        return self.store.list_metadata()

    def inspect_account(self, name: str) -> dict[str, str | None]:
        registry = self.store.load_registry()
        if name not in registry["accounts"]:
            raise ValueError(f"Unknown account: {name}")
        entry = registry["accounts"][name]
        return {
            "name": entry["name"],
            "managed_state": "managed",
            "auth_mode": entry["auth_mode"],
            "account_id": entry["account_id"],
            "created_at": entry["created_at"],
            "updated_at": entry["updated_at"],
            "last_refresh": entry["last_refresh"],
            "last_verified_at": entry["last_verified_at"],
        }

    def current_account(self) -> dict[str, str | None]:
        active_name = self.store.matched_active_name()
        live = self.store.read_live_auth()
        if active_name:
            return self.inspect_account(active_name)
        if live is None:
            raise ValueError("No current ~/.codex/auth.json was found")
        snapshot = parse_snapshot(live)
        return {
            "name": None,
            "managed_state": "unmanaged",
            "auth_mode": snapshot.auth_mode,
            "account_id": snapshot.account_id,
            "created_at": None,
            "updated_at": None,
            "last_refresh": snapshot.last_refresh,
            "last_verified_at": None,
        }

    def rename_account(self, old: str, new: str, *, force: bool) -> None:
        self.store.rename_snapshot(old, new, force=force)

    def remove_account(self, name: str, *, force_current: bool) -> None:
        self.store.remove_snapshot(name, force_current=force_current)

    def doctor(self) -> dict[str, str]:
        registry_valid = "true"
        live_auth_valid = "true"
        try:
            self.store.load_registry()
        except Exception:
            registry_valid = "false"
        try:
            live = self.store.read_live_auth()
            if live is not None:
                parse_snapshot(live)
        except Exception:
            live_auth_valid = "false"
        return {
            "codex_on_path": str(shutil.which(self.codex_executable, path=self.env.get("PATH") if self.env else None) is not None).lower(),
            "codex_dir": str(self.store.codex_dir),
            "live_auth_exists": str(self.store.live_auth_path.exists()).lower(),
            "live_auth_valid": live_auth_valid,
            "store_root": str(self.store.root),
            "registry_exists": str(self.store.registry_path.exists()).lower(),
            "registry_valid": registry_valid,
        }
```

```python
# src/codex_auth/cli.py
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

    subparsers.add_parser("doctor", help="Inspect local Codex and store state.")
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

    if args.command == "rename":
        service.rename_account(args.old, args.new, force=args.force)
        print(f"renamed: {args.old} -> {args.new}")
        return 0

    if args.command in {"remove", "rm"}:
        service.remove_account(args.name, force_current=args.force_current)
        print(f"removed: {args.name}")
        return 0

    if args.command == "doctor":
        print_kv_map(service.doctor())
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 1
```

- [ ] **Step 4: Run the admin-command CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli_admin_commands.py -v`
Expected: PASS

- [ ] **Step 5: Commit the administrative commands**

```bash
git add src/codex_auth/service.py src/codex_auth/cli.py tests/test_cli_admin_commands.py
git commit -m "feat: add admin and diagnostic cli commands"
```

### Task 7: Add README And CI Coverage For Installation And Release

**Files:**
- Create: `README.md`
- Create: `.github/workflows/ci.yml`
- Test: `tests/test_project_files.py`

- [ ] **Step 1: Write the failing project-file tests**

```python
# tests/test_project_files.py
from pathlib import Path


def test_readme_mentions_uv_install_and_codex_auth() -> None:
    text = Path("README.md").read_text()
    assert "uv tool install" in text
    assert "codex-auth" in text


def test_ci_workflow_exists() -> None:
    workflow = Path(".github/workflows/ci.yml")
    assert workflow.exists()
```

- [ ] **Step 2: Run the project-file tests to verify they fail**

Run: `uv run pytest tests/test_project_files.py -v`
Expected: FAIL with `FileNotFoundError: README.md`

- [ ] **Step 3: Write the README and CI workflow**

````markdown
# README.md
# codex-account-switcher

Manage multiple local Codex `auth.json` snapshots with a single CLI: `codex-auth`.

## Safety Model

- The tool stores local credential snapshots on the current machine only.
- It does not encrypt tokens in the first release.
- It never prints raw access, refresh, or ID tokens.
- The repository must never contain real credential snapshots.

## Install

For local development:

```bash
uv sync --dev
uv run codex-auth --help
```

After publishing this repository to GitHub, install it on another machine with `uv tool install` using the repository URL shown by GitHub.

## Commands

```bash
codex-auth save work
codex-auth ls
codex-auth current
codex-auth inspect work
codex-auth use work
codex-auth rename work primary
codex-auth rm primary --force-current
codex-auth doctor
```

## Development

```bash
uv run pytest -v
```
````

```yaml
# .github/workflows/ci.yml
name: ci

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv python install 3.12
      - run: uv sync --dev
      - run: uv run pytest -v
```

- [ ] **Step 4: Run the full test suite to verify the repo is green**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Commit the release docs and CI**

```bash
git add README.md .github/workflows/ci.yml tests/test_project_files.py
git commit -m "docs: add installation guide and ci workflow"
```
