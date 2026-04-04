# Codex Account Switcher Design

**Date:** 2026-04-04

**Goal:** Build a small command-line tool that manages multiple local Codex login snapshots and switches the active account quickly by replacing `~/.codex/auth.json`, then validating the result with `codex login status`.

## Scope

This design covers a first release focused on ChatGPT-backed Codex login state stored in `~/.codex/auth.json`.

Included:
- Save the current local Codex login state as a named account snapshot.
- Switch between saved account snapshots.
- Validate a switch by running `codex login status`.
- List, inspect, rename, remove, and diagnose saved accounts.
- Package the tool as a Python CLI that can be installed from GitHub with `uv tool install`.

Excluded from the first release:
- Managing `config.toml` profiles per account.
- Encrypted credential storage.
- Remote sync of credentials across machines.
- API-key-mode account management as a first-class feature.

The storage layout and command structure should remain extensible so later releases can add more auth modes without breaking the CLI.

## User Experience

The tool will expose a single CLI command: `codex-auth`.

Planned subcommands:
- `codex-auth save <name>`
- `codex-auth use <name>`
- `codex-auth list`
- `codex-auth ls`
- `codex-auth remove <name>`
- `codex-auth rm <name>`
- `codex-auth inspect <name>`
- `codex-auth current`
- `codex-auth rename <old> <new>`
- `codex-auth doctor`

Command behavior principles:
- Default to non-interactive behavior so the tool works in scripts.
- Never print raw access, refresh, or ID tokens.
- Favor explicit failures over silent recovery.
- Keep output short and readable.
- Make `ls` and `rm` first-class subcommands rather than shell aliases.

Expected common flow:
1. User logs in through Codex normally.
2. User runs `codex-auth save work`.
3. User logs in with another account.
4. User runs `codex-auth save personal`.
5. User runs `codex-auth use work` or `codex-auth use personal` to switch.

## Architecture

The tool will be a small Python package managed with `uv`, developed in:

`/home/zz/codex_workspace/codex-account-switcher`

The package should be structured into a few focused modules:
- CLI entrypoint and argument parsing.
- Auth snapshot validation and redaction helpers.
- Local account store management.
- Active account switching workflow.
- Codex integration for status verification.

The active Codex credential file remains the source of truth for the running Codex CLI:
- Active file: `~/.codex/auth.json`
- Tool-managed store: `~/.codex-account-switcher/`

This is intentionally a copy-based design, not a symlink-based design. Copy-based switching matches Codex's current behavior more closely, avoids confusing filesystem state, and is easier to inspect and repair by hand.

## Storage Design

Runtime account storage will live outside the repository:

- `~/.codex-account-switcher/accounts/<name>.json`
  Stores the raw saved `auth.json` snapshot for one account.
- `~/.codex-account-switcher/registry.json`
  Stores non-sensitive metadata used for listing, current-account tracking, and diagnostics.

`registry.json` should store:
- `version`
- `active_name`
- `accounts`

Each account entry in `accounts` should contain only non-sensitive metadata:
- `name`
- `auth_mode`
- `account_id`
- `created_at`
- `updated_at`
- `last_refresh`
- `last_verified_at`

Sensitive tokens must remain only in:
- `~/.codex/auth.json`
- `~/.codex-account-switcher/accounts/<name>.json`

Permissions requirements:
- Snapshot files must be written with mode `600`.
- The registry file can also be written with mode `600` for consistency.

## Account Identity Model

For the first release, an account snapshot is considered valid when:
- The file is valid JSON.
- `auth_mode` exists.
- The expected top-level structure exists.
- The snapshot contains the fields needed for the ChatGPT auth path now used by Codex:
  - `tokens.access_token`
  - `tokens.refresh_token`
  - `tokens.id_token`
  - `tokens.account_id`

The stable identity displayed to the user will be the saved account name plus the snapshot's `account_id`.
Managed-account matching should use `auth_mode` plus `account_id`, not snapshot file contents byte-for-byte, so routine token refreshes do not break identity tracking.

The tool must not assume that the current `~/.codex/auth.json` always belongs to a managed account. The current active file may have been changed manually or by another process. When the current file does not match any managed snapshot identity, the tool should report the current state as `unmanaged`.

## Switching Workflow

`codex-auth use <name>` should perform the following steps:

1. Load `registry.json`.
2. Confirm that `<name>` exists in the managed account store.
3. Load and validate `~/.codex-account-switcher/accounts/<name>.json`.
4. Read the current `~/.codex/auth.json`, if present.
5. If the registry says a managed account is currently active, and the current `auth.json` is readable, sync the current `auth.json` back into that managed account snapshot before switching.
6. Write the target snapshot to a temporary file next to `~/.codex/auth.json`.
7. Set the temporary file permission to `600`.
8. Atomically replace `~/.codex/auth.json` with the temporary file using rename semantics.
9. Run `codex login status`.
10. If verification succeeds, update `registry.json` with the new `active_name` and `last_verified_at`.
11. If verification fails, report that the file switch completed but validation failed. Do not automatically roll back.

The pre-switch sync is important because Codex may refresh tokens during normal use. Without syncing the current active file back into the store, managed snapshots would drift stale over time.

## Save Workflow

`codex-auth save <name>` should:

1. Validate the provided account name.
2. Read `~/.codex/auth.json`.
3. Validate that it is a supported ChatGPT auth snapshot.
4. Refuse to overwrite an existing saved account unless `--force` is provided.
5. Write the snapshot to `~/.codex-account-switcher/accounts/<name>.json` with mode `600`.
6. Upsert the non-sensitive metadata into `registry.json`.
7. Mark the saved account as the active managed account, because the snapshot was created from the current live `auth.json`.

## Listing and Inspection

`list` and `ls` should display:
- Account name
- Auth mode
- Account ID
- Updated time
- Whether the account is the active managed account

`inspect <name>` and `current` should display a concise summary:
- Name
- Managed or unmanaged state
- Auth mode
- Account ID
- Created time
- Updated time
- Snapshot `last_refresh`
- Registry `last_verified_at`

No token values may be shown.

## Removal and Rename

`remove` and `rm` should:
- Refuse to remove a missing account.
- Refuse to remove the currently active managed account unless `--force-current` is set.
- Require explicit confirmation only if the command is run in interactive mode without `--yes`.

`rename` should:
- Refuse to rename to an already existing name unless `--force` is set.
- Rename both the snapshot file and the registry entry.
- Preserve active-state tracking if the renamed account is active.

## Doctor Command

`doctor` should verify:
- `codex` executable is available on `PATH`.
- `~/.codex` exists or is at least creatable.
- `~/.codex/auth.json` is present and readable, or report that there is no current login.
- `~/.codex-account-switcher/` is present or creatable.
- Registry and snapshot files have parseable content.
- File permissions are sane enough for local secret storage.

The command should report findings clearly without changing any state.

## Installation and Distribution

The repository should be publishable to GitHub and installable on other machines with `uv`.

Primary installation path:

```bash
uv tool install git+https://github.com/namespace/codex-account-switcher.git
```

Optional SSH-based installation:

```bash
uv tool install git+ssh://git@github.com/namespace/codex-account-switcher.git
```

Temporary execution without installation:

```bash
uvx --from git+https://github.com/namespace/codex-account-switcher.git codex-auth ls
```

The package must expose a console entrypoint named `codex-auth`.

Repository requirements:
- Standard `pyproject.toml`
- Clear `README.md`
- `LICENSE`
- Tests runnable in CI
- `.gitignore` that excludes virtualenvs, caches, build artifacts, and any local test fixtures containing secrets

The repository must never contain real credential snapshots.

## Error Handling

Error handling must be explicit and predictable.

Rules:
- Invalid JSON is a hard failure.
- Missing required auth fields is a hard failure.
- Missing target account on `use`, `inspect`, `remove`, or `rename` is a hard failure.
- Verification failure after `use` is reported as a partial success:
  - the active file was switched
  - Codex verification failed
- The tool should not silently create fake defaults for missing credential files.

Recommended error categories:
- Usage errors
- Local filesystem errors
- Snapshot validation errors
- Codex verification errors

## Security Constraints

This tool is a local convenience layer around credential files. It is not a secret-management system.

Security requirements:
- Never print tokens.
- Never log tokens.
- Never store tokens in metadata.
- Keep snapshot and registry files out of the repository.
- Use restrictive file permissions.
- Make it obvious in documentation that GitHub distribution covers tool code only, not any saved account data.

Future encryption support is allowed, but not required in the first release.

## Testing Strategy

Development should follow TDD.

Test layers:

1. Unit tests
   Cover name validation, snapshot validation, metadata extraction, redaction, and registry logic.

2. Filesystem workflow tests
   Use temporary directories to simulate:
   - `~/.codex/auth.json`
   - `~/.codex-account-switcher/`
   - atomic write and rename behavior

3. CLI integration tests
   Execute real CLI commands against a temporary home directory.

4. Verification-path tests
   Stub a fake `codex` executable on `PATH` so tests can cover:
   - successful `codex login status`
   - failing `codex login status`
   - missing `codex`

The tests must cover both success paths and failure paths, including unmanaged current state and partial-success verification failures.

## Non-Goals

The first release should avoid scope creep.

Not in scope:
- Syncing account snapshots through GitHub or any remote store
- Sharing one snapshot store across multiple users
- Managing browser cookies or external OpenAI login state
- Editing or interpreting Codex internal SQLite databases
- Auto-healing broken Codex auth files

## Open Extension Path

The design should keep room for later additions without breaking the CLI:
- Support API-key-mode snapshots in a later version.
- Support optional per-account `config.toml` bundles in a later version.
- Support export and import of account bundles with explicit user action.

Those are future extensions, not first-release requirements.
