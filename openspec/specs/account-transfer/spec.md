# account-transfer Specification

## Purpose
TBD - created by archiving change account-transfer-v0-2-0. Update Purpose after archive.
## Requirements
### Requirement: Export selected accounts into an encrypted archive

The tool SHALL export one or more selected managed accounts into a single encrypted transfer archive file.

#### Scenario: Export multiple managed accounts
- **WHEN** the operator selects multiple saved accounts for export and provides a valid passphrase
- **THEN** the tool writes one transfer archive containing only the selected accounts

#### Scenario: Reject export when no saved accounts are available
- **WHEN** the operator runs `export` but the managed store contains no saved accounts
- **THEN** the tool rejects the export instead of creating an empty archive

### Requirement: Collect transfer passphrases securely

The tool SHALL require a non-empty transfer passphrase for export and import, either from an interactive prompt or from a single-line passphrase file.

#### Scenario: Enter a passphrase interactively for export
- **WHEN** the operator does not supply `--passphrase-file` during export
- **THEN** the tool prompts for a non-empty passphrase and requires confirmation before proceeding

#### Scenario: Read a passphrase from a file
- **WHEN** the operator supplies `--passphrase-file`
- **THEN** the tool reads exactly one non-empty line from that file and rejects blank or multi-line passphrase files

### Requirement: Require interactive account selection for transfer operations

The tool SHALL require an interactive terminal for choosing which accounts are exported or imported.

#### Scenario: Select accounts for export
- **WHEN** the operator runs `export` in an interactive terminal
- **THEN** the tool presents a batch account selector before writing the archive

#### Scenario: Reject transfer selection in a non-interactive terminal
- **WHEN** the operator runs `export` or `import` without an interactive terminal
- **THEN** the tool rejects the operation instead of guessing a default selection

### Requirement: Import selected accounts from an encrypted archive

The tool SHALL decrypt a transfer archive with the supplied passphrase, validate its contents, and allow the operator to select which archive accounts to import.

#### Scenario: Import a selected subset of archive accounts
- **WHEN** the operator opens a valid archive, supplies the correct passphrase, and selects a subset of the contained accounts
- **THEN** the tool imports only the selected accounts into the managed store

#### Scenario: Reject an unreadable archive
- **WHEN** the archive cannot be decrypted with the supplied passphrase or fails validation
- **THEN** the tool rejects the import and reports that the passphrase is incorrect or the file is damaged

### Requirement: Resolve import name conflicts explicitly

The tool SHALL require an explicit resolution for each selected imported account whose target name already exists locally.

#### Scenario: Skip an imported account that conflicts
- **WHEN** an imported account name already exists locally and the operator chooses `skip`
- **THEN** the tool leaves the existing local snapshot unchanged and does not import that archive account

#### Scenario: Overwrite an imported account that conflicts
- **WHEN** an imported account name already exists locally and the operator chooses `overwrite`
- **THEN** the tool replaces the existing local snapshot and registry metadata for that name with the imported account

#### Scenario: Rename an imported account that conflicts
- **WHEN** an imported account name already exists locally and the operator chooses `rename` with a valid unused replacement name
- **THEN** the tool imports the archive account under the replacement name and preserves the original local account

### Requirement: Preserve the current live session during import

The tool SHALL treat import as managed-store maintenance only and SHALL NOT switch or verify the current live auth session.

#### Scenario: Import accounts without changing the live auth file
- **WHEN** the operator completes an import
- **THEN** the tool writes the imported managed snapshots and registry metadata without overwriting `~/.codex/auth.json`

#### Scenario: Import accounts without changing the active managed account
- **WHEN** the operator completes an import while another managed account is active
- **THEN** the tool preserves the existing active managed account instead of activating one of the imported accounts

