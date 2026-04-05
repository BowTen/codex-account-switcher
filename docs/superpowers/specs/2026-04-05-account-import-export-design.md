# Account Import Export Design

**Date:** 2026-04-05

**Goal:** Add encrypted account export and import workflows so users can move saved Codex login snapshots between machines without manually copying store files.

## Scope

This design extends the existing local snapshot manager with migration features for saved accounts.

Included:
- Export one or more saved accounts into a single encrypted transfer file.
- Support interactive batch selection of accounts during export.
- Import one or more accounts from an encrypted transfer file.
- Support interactive batch selection of accounts during import.
- Resolve name conflicts interactively during import with skip, overwrite, or rename.
- Support interactive passphrase entry and non-interactive passphrase loading from a file.

Excluded from this design:
- Exporting the current unmanaged `~/.codex/auth.json` directly.
- Automatic account switching after import.
- Remote synchronization or cloud storage.
- Cross-version migration guarantees beyond explicit format versioning.

## User Experience

Two new commands will be added:

- `codex-auth export`
- `codex-auth import <file>`

### Export Workflow

`codex-auth export` should:

1. Load the saved account list from the local store.
2. Open an interactive multi-select prompt so the user can choose one or more saved accounts to export.
3. Prompt for the output file path, defaulting to a local filename such as `./codex-auth-export.cae`.
4. Prompt for an encryption passphrase and confirm it.
5. Allow non-interactive passphrase input through `--passphrase-file <path>` instead of terminal prompts.
6. Write one encrypted export file containing all selected accounts.
7. Print a concise success message with the number of exported accounts and output path.

### Import Workflow

`codex-auth import <file>` should:

1. Load the encrypted transfer file.
2. Prompt for the decryption passphrase, unless `--passphrase-file <path>` is provided.
3. Decrypt and validate the transfer payload.
4. Show the accounts available in the transfer file through an interactive multi-select prompt.
5. Let the user choose which imported accounts to apply locally.
6. For each selected account whose name already exists locally, prompt for a conflict action:
   - `skip`
   - `overwrite`
   - `rename`
7. If the user chooses `rename`, prompt for a new name and validate it immediately.
8. Write imported snapshots into the local managed store.
9. Print a concise summary of imported, skipped, overwritten, and renamed accounts.

### Interaction Principles

- The selection UI should use a terminal interactive prompt library rather than custom number parsing.
- The project should use `InquirerPy` for multi-select and choice prompts.
- Password prompts should hide typed characters.
- In a non-interactive terminal, `export` and `import` should fail clearly because account selection is intentionally interactive, even if `--passphrase-file` is provided.
- Existing commands such as `save`, `use`, `list`, `inspect`, and `doctor` must keep their current behavior.

## Architecture

The new feature should preserve the current `argparse` entrypoint and layer the transfer workflow on top of the existing store and service boundaries.

Recommended module layout:

- `src/codex_auth/cli.py`
  Add `export` and `import` command parsing and dispatch.
- `src/codex_auth/service.py`
  Add transfer orchestration methods that assemble store data, call prompt helpers, and apply import decisions.
- `src/codex_auth/store.py`
  Add reusable helpers for batch loading snapshots and importing snapshots with explicit metadata handling.
- `src/codex_auth/models.py`
  Add small data models for transfer payloads and import conflict decisions.
- `src/codex_auth/transfer.py`
  Handle transfer file serialization, encryption, decryption, and version validation.
- `src/codex_auth/prompts.py`
  Isolate all `InquirerPy`-based interactive prompts from business logic.
- `src/codex_auth/errors.py`
  Hold dedicated exceptions for invalid transfer files, wrong passphrases, and unresolved import conflicts.

The key boundary is:
- `service.py` owns workflow and state transitions.
- `transfer.py` owns encrypted file format logic.
- `prompts.py` owns terminal interaction.

This keeps the transfer format testable without a real terminal and keeps the interactive layer thin.

## Transfer File Format

The transfer file should use a dedicated extension such as `.cae`.

The file should contain two logical layers:

1. A small unencrypted header with decryption metadata.
2. An encrypted JSON payload containing the actual account data.

### Unencrypted Header

The header should include only fields needed to derive the key and decrypt the payload:

- `format_version`
- `kdf`
- `kdf_params`
- `cipher`
- `nonce`

No account names, metadata, or token values should appear in the unencrypted header.

### Encrypted Payload

The encrypted payload JSON should include:

- Export timestamp
- Tool version
- Account entries

Each account entry should include:

- `name`
- `metadata`
- `snapshot`

Including both metadata and raw snapshot content allows the importer to display account summaries before local write operations while still restoring the full managed snapshot faithfully.

## Encryption Design

The export file should use password-based encryption implemented with `cryptography`.

Recommended choices:

- Key derivation: `scrypt`
- Symmetric cipher: `AESGCM`

Reasons:
- `scrypt` is appropriate for passphrase-derived keys and raises the cost of brute-force guessing.
- `AES-GCM` provides both confidentiality and integrity checking.
- `cryptography` is a standard, stable dependency for Python CLI tooling.

Failure behavior:

- If the passphrase is wrong, import should fail with a concise error such as "invalid passphrase or corrupted file".
- If the payload format is invalid or the file has been tampered with, import should fail with the same class of user-facing error rather than leaking low-level decrypt details.
- The code should validate `format_version` before assuming payload structure so later versions can evolve cleanly.

## Import Conflict Handling

The import flow should separate account selection from conflict resolution.

### Selection

The user first selects which accounts from the transfer file should be imported.

### Conflict Resolution

For each selected account that conflicts with an existing local account name, the importer should prompt for one of:

- `skip`
- `overwrite`
- `rename`

If `rename` is chosen:

- The new name must satisfy the existing account name validator.
- The new name must not collide with any existing local account.
- The new name must not collide with another account chosen in the same import batch.

This resolution should happen before any files are written so the import plan is fully known in advance.

## Local State Effects

Importing accounts should update only the managed store:

- Write snapshots to `~/.codex-account-switcher/accounts/<name>.json`
- Upsert corresponding registry metadata

Import must not:

- Modify `~/.codex/auth.json`
- Change `registry.json.active_name`
- Automatically run `codex login status`
- Automatically switch the currently active account

This keeps import semantics clear: importing makes accounts available on the machine, while `codex-auth use <name>` remains the explicit switch operation.

Export should read only from the managed store. It should not silently include the live unmanaged auth file.

## Data Validation

The transfer workflow should reuse the existing snapshot validation logic wherever possible.

Validation rules:

- Every exported snapshot must already parse as a supported managed account snapshot.
- Imported payload entries must contain valid metadata and valid raw snapshots.
- Unsupported transfer `format_version` values should fail fast.
- Empty export selections should cancel without writing a file.
- Empty import selections should cancel without changing local state.

## Testing Strategy

The feature should be implemented with test-first changes and verified mainly at the transfer and service layers.

### Transfer Tests

Add `tests/test_transfer.py` to cover:

- Encrypting and decrypting a multi-account transfer payload.
- Rejecting wrong passphrases.
- Rejecting malformed files.
- Rejecting unsupported format versions.

### Service Tests

Extend `tests/test_service.py` to cover:

- Exporting a selected subset of managed accounts.
- Importing a selected subset from a transfer payload.
- Overwriting an existing local account during import.
- Renaming an imported account during conflict resolution.
- Leaving `active_name` unchanged after import.
- Leaving `~/.codex/auth.json` unchanged after import.

### CLI Tests

Add CLI-level tests in `tests/test_cli_admin_commands.py` or a new `tests/test_cli_transfer_commands.py` to cover:

- New command parsing.
- Clear failure in non-interactive mode when required prompts cannot run.
- Passphrase-file based import and export paths.
- Wiring from CLI into prompt and service layers.

### Prompt Testing Boundary

Do not build fragile end-to-end terminal UI replay tests for `InquirerPy`.
Instead:

- Keep prompt code isolated in `prompts.py`.
- Mock prompt helper return values in CLI or service tests.
- Test the actual business outcomes rather than the library's own rendering behavior.

## Documentation

The README should be updated to document:

- New `export` and `import` commands.
- The fact that exported files are passphrase-protected credential bundles.
- The fact that these files remain highly sensitive and should be stored and shared carefully.
- The requirement for an interactive terminal unless non-interactive passphrase input is fully provided.

## Risks and Tradeoffs

- Adding `InquirerPy` and `cryptography` introduces the first runtime dependencies for the project, but both are justified by the new terminal UX and encryption requirements.
- A transfer format version is necessary from the first release of this feature to avoid locking the project into an implicit schema.
- The tool should prefer explicit failure over partial import when payload validation or conflict planning is incomplete.
- Importing without switching avoids surprising state changes, but it means the user still needs a second explicit `use` command after moving accounts to a new machine.
