# Account Import Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add encrypted import and export commands that let users interactively batch-select saved accounts, write them into a passphrase-protected transfer file, and import selected accounts on another machine with interactive conflict resolution.

**Architecture:** Keep the current `argparse` CLI and existing service/store split. Add a focused transfer module for the encrypted archive format, a prompts module for `InquirerPy` terminal interaction, and service methods that orchestrate export/import workflows without directly rendering prompts. The import path updates only the managed store and never mutates the live `~/.codex/auth.json`.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `InquirerPy`, `cryptography`, existing `argparse` CLI

---

### Task 1: Add Transfer Format Primitives

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/codex_auth/models.py`
- Create: `src/codex_auth/errors.py`
- Create: `src/codex_auth/transfer.py`
- Test: `tests/test_transfer.py`

- [ ] **Step 1: Write the failing transfer round-trip and validation tests**

```python
import pytest

from codex_auth.errors import InvalidPassphraseError, InvalidTransferFileError
from codex_auth.transfer import decrypt_transfer_bytes, encrypt_transfer_bytes


def make_archive() -> dict[str, object]:
    return {
        "exported_at": "2026-04-05T10:00:00Z",
        "tool_version": "0.1.0",
        "accounts": [
            {
                "name": "work",
                "metadata": {
                    "name": "work",
                    "auth_mode": "chatgpt",
                    "account_id": "acct-work",
                    "created_at": "2026-04-05T09:00:00Z",
                    "updated_at": "2026-04-05T09:00:00Z",
                    "last_refresh": "2026-04-05T08:00:00Z",
                    "last_verified_at": None,
                },
                "snapshot": {
                    "auth_mode": "chatgpt",
                    "last_refresh": "2026-04-05T08:00:00Z",
                    "tokens": {
                        "access_token": "access-work",
                        "refresh_token": "refresh-work",
                        "id_token": "id-work",
                        "account_id": "acct-work",
                    },
                },
            }
        ],
    }


def test_encrypt_and_decrypt_transfer_bytes_round_trip() -> None:
    archive = make_archive()

    blob = encrypt_transfer_bytes(archive, passphrase="secret-pass")
    restored = decrypt_transfer_bytes(blob, passphrase="secret-pass")

    assert restored["accounts"][0]["name"] == "work"
    assert restored["accounts"][0]["snapshot"]["tokens"]["account_id"] == "acct-work"


def test_decrypt_transfer_bytes_rejects_wrong_passphrase() -> None:
    blob = encrypt_transfer_bytes(make_archive(), passphrase="secret-pass")

    with pytest.raises(InvalidPassphraseError):
        decrypt_transfer_bytes(blob, passphrase="wrong-pass")


def test_decrypt_transfer_bytes_rejects_unsupported_format_version() -> None:
    blob = encrypt_transfer_bytes(make_archive(), passphrase="secret-pass")
    mutated = blob.replace(b'"format_version": 1', b'"format_version": 999', 1)

    with pytest.raises(InvalidTransferFileError, match="Unsupported transfer format"):
        decrypt_transfer_bytes(mutated, passphrase="secret-pass")
```

- [ ] **Step 2: Run the transfer tests to verify they fail**

Run: `uv run pytest tests/test_transfer.py -q`
Expected: FAIL with import errors because `codex_auth.errors` and `codex_auth.transfer` do not exist yet.

- [ ] **Step 3: Add the runtime dependencies and transfer models**

```toml
[project]
dependencies = [
  "InquirerPy>=0.3,<0.4",
  "cryptography>=44,<45",
]
```

```python
@dataclass(slots=True)
class TransferAccount:
    name: str
    metadata: dict[str, str | None]
    snapshot: dict[str, Any]


@dataclass(slots=True)
class ImportPlanItem:
    source_name: str
    target_name: str
    action: str
```

```python
class TransferError(ValueError):
    pass


class InvalidTransferFileError(TransferError):
    pass


class InvalidPassphraseError(TransferError):
    pass


class InteractiveRequiredError(TransferError):
    pass
```

- [ ] **Step 4: Implement minimal archive encryption and decryption**

```python
FORMAT_VERSION = 1
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def encrypt_transfer_bytes(payload: dict[str, Any], *, passphrase: str) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(passphrase.encode())
    plaintext = json.dumps(payload, sort_keys=True).encode()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    envelope = {
        "format_version": FORMAT_VERSION,
        "kdf": "scrypt",
        "kdf_params": {"salt": base64.b64encode(salt).decode(), "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P},
        "cipher": "aes-256-gcm",
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    return json.dumps(envelope, indent=2, sort_keys=True).encode() + b"\n"


def decrypt_transfer_bytes(blob: bytes, *, passphrase: str) -> dict[str, Any]:
    try:
        envelope = json.loads(blob.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTransferFileError("Invalid transfer file") from exc
    if envelope.get("format_version") != FORMAT_VERSION:
        raise InvalidTransferFileError("Unsupported transfer format")
    try:
        salt = base64.b64decode(envelope["kdf_params"]["salt"])
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
        key = Scrypt(
            salt=salt,
            length=32,
            n=envelope["kdf_params"]["n"],
            r=envelope["kdf_params"]["r"],
            p=envelope["kdf_params"]["p"],
        ).derive(passphrase.encode())
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode())
    except InvalidTag as exc:
        raise InvalidPassphraseError("Invalid passphrase or corrupted file") from exc
    except Exception as exc:
        raise InvalidTransferFileError("Invalid transfer file") from exc
```

- [ ] **Step 5: Run the transfer tests to verify they pass**

Run: `uv run pytest tests/test_transfer.py -q`
Expected: PASS with `3 passed`.

- [ ] **Step 6: Commit the transfer format foundation**

```bash
git add pyproject.toml src/codex_auth/models.py src/codex_auth/errors.py src/codex_auth/transfer.py tests/test_transfer.py
git commit -m "feat: add encrypted transfer archive format"
```

### Task 2: Add Store and Service Import Export Workflow

**Files:**
- Modify: `src/codex_auth/models.py`
- Modify: `src/codex_auth/store.py`
- Modify: `src/codex_auth/service.py`
- Test: `tests/test_service.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing store and service tests for export subset and import side effects**

```python
def test_export_accounts_writes_only_selected_accounts(tmp_path) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)

    archive = service.build_export_archive(["work"])

    assert [item.name for item in archive.accounts] == ["work"]


def test_import_accounts_overwrites_and_renames_without_touching_live_auth(tmp_path) -> None:
    service = CodexAuthService(home=tmp_path)
    service.store.save_snapshot("work", make_snapshot("acct-old-work"), force=False, mark_active=True)
    service.store.write_live_auth(make_snapshot("acct-live"))
    active_before = service.store.current_active_name()

    archive = TransferArchive(
        exported_at="2026-04-05T10:00:00Z",
        tool_version="0.1.0",
        accounts=[
            TransferAccount(name="work", metadata=build_metadata("work", parse_snapshot(make_snapshot("acct-new-work"))).to_dict(), snapshot=make_snapshot("acct-new-work")),
            TransferAccount(name="travel", metadata=build_metadata("travel", parse_snapshot(make_snapshot("acct-travel"))).to_dict(), snapshot=make_snapshot("acct-travel")),
        ],
    )
    plan = [
        ImportPlanItem(source_name="work", target_name="work", action="overwrite"),
        ImportPlanItem(source_name="travel", target_name="vacation", action="rename"),
    ]

    result = service.apply_import_archive(archive, plan)

    assert result.imported == ["work", "vacation"]
    assert service.store.load_snapshot("work").account_id == "acct-new-work"
    assert service.store.load_snapshot("vacation").account_id == "acct-travel"
    assert service.store.read_live_auth()["tokens"]["account_id"] == "acct-live"
    assert service.store.current_active_name() == active_before
```

```python
def test_import_snapshots_rejects_duplicate_target_names(tmp_path) -> None:
    store = AccountStore(tmp_path)
    archive_accounts = [
        TransferAccount(name="work", metadata={}, snapshot=make_snapshot("acct-work")),
        TransferAccount(name="personal", metadata={}, snapshot=make_snapshot("acct-personal")),
    ]
    plan = [
        ImportPlanItem(source_name="work", target_name="shared", action="rename"),
        ImportPlanItem(source_name="personal", target_name="shared", action="rename"),
    ]

    with pytest.raises(ValueError, match="Duplicate import target name: shared"):
        store.import_snapshots(archive_accounts, plan)
```

- [ ] **Step 2: Run the store and service tests to verify they fail**

Run: `uv run pytest tests/test_service.py tests/test_store.py -q`
Expected: FAIL because `build_export_archive()`, `apply_import_archive()`, and `import_snapshots()` do not exist yet.

- [ ] **Step 3: Add the import/export workflow models and store helpers**

```python
@dataclass(slots=True)
class TransferArchive:
    exported_at: str
    tool_version: str
    accounts: list[TransferAccount]


@dataclass(slots=True)
class ImportResult:
    imported: list[str]
    overwritten: list[str]
    renamed: list[str]
    skipped: list[str]
```

```python
def load_snapshots(self, names: list[str]) -> list[tuple[AccountMetadata, AccountSnapshot]]:
    registry = self.load_registry()
    items: list[tuple[AccountMetadata, AccountSnapshot]] = []
    for name in names:
        entry = registry["accounts"].get(name)
        if entry is None:
            raise ValueError(f"Unknown account: {name}")
        items.append((AccountMetadata(**entry), self.load_snapshot(name)))
    return items


def import_snapshots(self, accounts: list[TransferAccount], plan: list[ImportPlanItem]) -> ImportResult:
    original_active = self.current_active_name()
    imported: list[str] = []
    overwritten: list[str] = []
    renamed: list[str] = []
    skipped: list[str] = []
    seen_targets: set[str] = set()
    account_by_name = {account.name: account for account in accounts}
    for item in plan:
        if item.action == "skip":
            skipped.append(item.source_name)
            continue
        if item.target_name in seen_targets:
            raise ValueError(f"Duplicate import target name: {item.target_name}")
        seen_targets.add(item.target_name)
        account = account_by_name[item.source_name]
        self.save_snapshot(item.target_name, account.snapshot, force=item.action == "overwrite", mark_active=False)
        imported.append(item.target_name)
        if item.action == "overwrite":
            overwritten.append(item.target_name)
        if item.target_name != item.source_name:
            renamed.append(item.target_name)
    if original_active is not None:
        registry = self.load_registry()
        registry["active_name"] = original_active
        self.save_registry(registry)
    return ImportResult(imported=imported, overwritten=overwritten, renamed=renamed, skipped=skipped)
```

- [ ] **Step 4: Implement the service methods with no prompt rendering**

```python
def build_export_archive(self, names: list[str]) -> TransferArchive:
    if not names:
        raise ValueError("No accounts selected for export")
    accounts = []
    for metadata, snapshot in self.store.load_snapshots(names):
        accounts.append(
            TransferAccount(
                name=metadata.name,
                metadata=metadata.to_dict(),
                snapshot=snapshot.raw,
            )
        )
    return TransferArchive(
        exported_at=utc_now_iso(),
        tool_version="0.1.0",
        accounts=accounts,
    )


def write_export_archive(self, names: list[str], output_path: Path, *, passphrase: str) -> None:
    archive = self.build_export_archive(names)
    write_transfer_file(output_path, archive, passphrase=passphrase)


def read_import_archive(self, input_path: Path, *, passphrase: str) -> TransferArchive:
    return read_transfer_file(input_path, passphrase=passphrase)


def apply_import_archive(self, archive: TransferArchive, plan: list[ImportPlanItem]) -> ImportResult:
    return self.store.import_snapshots(archive.accounts, plan)
```

- [ ] **Step 5: Run the store and service tests to verify they pass**

Run: `uv run pytest tests/test_service.py tests/test_store.py -q`
Expected: PASS with the new import/export tests green and no regressions in the existing store/service tests.

- [ ] **Step 6: Commit the workflow layer**

```bash
git add src/codex_auth/models.py src/codex_auth/store.py src/codex_auth/service.py tests/test_service.py tests/test_store.py
git commit -m "feat: add account transfer workflow"
```

### Task 3: Add Interactive Prompt Adapters

**Files:**
- Create: `src/codex_auth/prompts.py`
- Modify: `src/codex_auth/models.py`
- Test: `tests/test_cli_transfer_commands.py`

- [ ] **Step 1: Write the failing CLI-facing tests for interactive guard and prompt wiring**

```python
def test_export_requires_interactive_terminal(tmp_path) -> None:
    result = run_cli(tmp_path, "export", "--passphrase-file", str(tmp_path / "pass.txt"))

    assert result.returncode == 1
    assert "error: export requires an interactive terminal" in result.stderr


def test_import_requires_interactive_terminal_even_with_passphrase_file(tmp_path) -> None:
    transfer_path = tmp_path / "accounts.cae"
    transfer_path.write_text("not-used-in-this-test")

    result = run_cli(tmp_path, "import", str(transfer_path), "--passphrase-file", str(tmp_path / "pass.txt"))

    assert result.returncode == 1
    assert "error: import requires an interactive terminal" in result.stderr
```

- [ ] **Step 2: Run the CLI transfer tests to verify they fail**

Run: `uv run pytest tests/test_cli_transfer_commands.py -q`
Expected: FAIL because the new test file references `export` and `import` commands that are not wired yet.

- [ ] **Step 3: Implement the prompt helpers around `InquirerPy`**

```python
def require_interactive(command_name: str, *, stdin: TextIO = sys.stdin) -> None:
    if not stdin.isatty():
        raise InteractiveRequiredError(f"{command_name} requires an interactive terminal")


def prompt_select_saved_accounts(accounts: list[AccountMetadata], *, message: str) -> list[str]:
    choices = [
        Choice(value=item.name, name=f"{item.name}  {item.auth_mode}  {item.account_id}")
        for item in accounts
    ]
    return inquirer.checkbox(message=message, choices=choices, instruction="Space to toggle, Enter to confirm").execute()


def prompt_select_archive_accounts(accounts: list[TransferAccount]) -> list[str]:
    choices = [
        Choice(value=item.name, name=f"{item.name}  {item.metadata['auth_mode']}  {item.metadata['account_id']}")
        for item in accounts
    ]
    return inquirer.checkbox(message="Select accounts to import", choices=choices).execute()


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
            planned_targets.add(account.name)
            plan.append(ImportPlanItem(source_name=account.name, target_name=account.name, action="import"))
            continue
        action = prompt_conflict_action(account.name)
        if action == "skip":
            plan.append(ImportPlanItem(source_name=account.name, target_name=account.name, action="skip"))
            continue
        if action == "overwrite":
            plan.append(ImportPlanItem(source_name=account.name, target_name=account.name, action="overwrite"))
            continue
        new_name = validate_account_name(prompt_new_account_name(account.name))
        if new_name in existing_names or new_name in planned_targets:
            raise ValueError(f"Account already exists: {new_name}")
        planned_targets.add(new_name)
        plan.append(ImportPlanItem(source_name=account.name, target_name=new_name, action="rename"))
    return plan
```

- [ ] **Step 4: Re-run the CLI transfer tests and fix the interactive guard behavior**

Run: `uv run pytest tests/test_cli_transfer_commands.py -q`
Expected: Still FAIL, but now the failure should move from missing prompt helpers to missing CLI command wiring.

- [ ] **Step 5: Commit the prompt adapter layer**

```bash
git add src/codex_auth/prompts.py src/codex_auth/models.py tests/test_cli_transfer_commands.py
git commit -m "feat: add interactive transfer prompts"
```

### Task 4: Wire Export Import Commands Into the CLI

**Files:**
- Modify: `src/codex_auth/cli.py`
- Modify: `src/codex_auth/service.py`
- Modify: `src/codex_auth/transfer.py`
- Modify: `tests/test_cli_transfer_commands.py`
- Modify: `tests/test_cli_read_commands.py`

- [ ] **Step 1: Extend the failing CLI tests to cover end-to-end command wiring**

```python
def test_cli_export_writes_encrypted_transfer_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    service = CodexAuthService()
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    service.store.save_snapshot("personal", make_snapshot("acct-personal"), force=False, mark_active=False)
    output_path = tmp_path / "accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr("codex_auth.prompts.prompt_select_saved_accounts", lambda accounts, message: ["work", "personal"])
    monkeypatch.setattr("codex_auth.prompts.prompt_export_path", lambda default_path: output_path)

    assert cli_main(["export", "--passphrase-file", str(pass_file)]) == 0
    assert output_path.exists()


def test_cli_import_applies_selected_accounts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source_home = tmp_path / "source-home"
    service = CodexAuthService(home=source_home)
    service.store.save_snapshot("work", make_snapshot("acct-work"), force=False, mark_active=True)
    archive_path = tmp_path / "accounts.cae"
    pass_file = tmp_path / "pass.txt"
    pass_file.write_text("secret-pass\n")
    service.write_export_archive(["work"], archive_path, passphrase="secret-pass")

    monkeypatch.setattr("codex_auth.prompts.require_interactive", lambda command_name: None)
    monkeypatch.setattr("codex_auth.prompts.prompt_select_archive_accounts", lambda accounts: ["work"])
    monkeypatch.setattr("codex_auth.prompts.build_import_plan", lambda archive_accounts, existing_accounts, selected_names: [ImportPlanItem(source_name="work", target_name="work", action="import")])

    assert cli_main(["import", str(archive_path), "--passphrase-file", str(pass_file)]) == 0
```

- [ ] **Step 2: Run the CLI tests to verify they fail for the expected command wiring reasons**

Run: `uv run pytest tests/test_cli_transfer_commands.py tests/test_cli_read_commands.py -q`
Expected: FAIL because `build_parser()` and `main()` do not yet understand `export`, `import`, or `--passphrase-file`.

- [ ] **Step 3: Add the new CLI arguments and passphrase file loading**

```python
export_parser = subparsers.add_parser("export", help="Export saved accounts into an encrypted transfer file.")
export_parser.add_argument("--passphrase-file")

import_parser = subparsers.add_parser("import", help="Import saved accounts from an encrypted transfer file.")
import_parser.add_argument("file")
import_parser.add_argument("--passphrase-file")
```

```python
def read_passphrase_from_file(path: str) -> str:
    content = Path(path).read_text().splitlines()
    if not content or not content[0].strip():
        raise ValueError(f"Passphrase file is empty: {path}")
    return content[0].strip()
```

- [ ] **Step 4: Implement the command handlers around prompts and service methods**

```python
if args.command == "export":
    prompts.require_interactive("export")
    accounts = service.list_accounts()
    selected_names = prompts.prompt_select_saved_accounts(accounts, message="Select accounts to export")
    if not selected_names:
        raise ValueError("No accounts selected for export")
    output_path = prompts.prompt_export_path(Path.cwd() / "codex-auth-export.cae")
    passphrase = read_passphrase_from_file(args.passphrase_file) if args.passphrase_file else prompts.prompt_passphrase(confirm=True)
    service.write_export_archive(selected_names, output_path, passphrase=passphrase)
    print(f"exported: {len(selected_names)} accounts -> {output_path}")
    return 0

if args.command == "import":
    prompts.require_interactive("import")
    passphrase = read_passphrase_from_file(args.passphrase_file) if args.passphrase_file else prompts.prompt_passphrase(confirm=False)
    archive = service.read_import_archive(Path(args.file), passphrase=passphrase)
    selected_names = set(prompts.prompt_select_archive_accounts(archive.accounts))
    plan = prompts.build_import_plan(archive.accounts, service.list_accounts(), selected_names)
    result = service.apply_import_archive(archive, plan)
    print(f"imported: {', '.join(result.imported)}")
    return 0
```

- [ ] **Step 5: Run the CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli_transfer_commands.py tests/test_cli_read_commands.py -q`
Expected: PASS with the new transfer command tests green and the existing read-command tests still passing.

- [ ] **Step 6: Commit the CLI integration**

```bash
git add src/codex_auth/cli.py src/codex_auth/service.py src/codex_auth/transfer.py tests/test_cli_transfer_commands.py tests/test_cli_read_commands.py
git commit -m "feat: add import and export commands"
```

### Task 5: Finish Docs and Run Full Verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_project_files.py`
- Modify: `docs/superpowers/specs/2026-04-05-account-import-export-design.md` (only if implementation drift requires a doc correction)

- [ ] **Step 1: Write the failing documentation and project-file checks**

```python
def test_readme_mentions_transfer_commands() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "codex-auth export" in readme
    assert "codex-auth import <file>" in readme
    assert "passphrase-protected credential bundles" in readme
```

- [ ] **Step 2: Run the documentation-focused tests to verify they fail**

Run: `uv run pytest tests/test_project_files.py -q`
Expected: FAIL because the README does not yet mention import/export commands or transfer-file sensitivity.

- [ ] **Step 3: Update the README with the new command examples and safety notes**

```markdown
## 功能概览

- 保存当前 `~/.codex/auth.json` 为命名快照。
- 在多个已保存账号之间切换当前登录状态。
- 交互式批量导出已保存账号到加密迁移文件。
- 交互式批量导入其他机器导出的账号迁移文件。
```

```markdown
## 命令示例

    codex-auth export
    codex-auth import ./codex-auth-export.cae
```

```markdown
## 安全说明

- 导出文件是带口令保护的凭证迁移包，仍然属于高敏感文件。
- 导入和导出需要交互式终端来选择账号。
```

- [ ] **Step 4: Run the full test suite and verify everything passes**

Run: `uv sync --dev`
Expected: dependencies install successfully into the project environment.

Run: `uv run pytest -q`
Expected: PASS with all existing and new tests green.

- [ ] **Step 5: Inspect the final diff and commit the documentation and verification pass**

```bash
git status --short
git diff --stat
git add README.md tests/test_project_files.py
git commit -m "docs: document encrypted account transfer"
```
