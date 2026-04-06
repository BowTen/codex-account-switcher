## ADDED Requirements

### Requirement: Save named managed snapshots

The tool SHALL save the current `~/.codex/auth.json` as a named managed snapshot when the operator runs `save` with a valid account name.

#### Scenario: Save a new snapshot
- **WHEN** a live auth file exists and the requested account name is unused
- **THEN** the tool saves the snapshot under the managed store, records metadata in the registry, and marks that account as active

#### Scenario: Reject duplicate snapshot names without force
- **WHEN** the requested account name already exists and `--force` is not supplied
- **THEN** the tool rejects the save and preserves the existing snapshot and registry entry

### Requirement: List and inspect managed snapshots without exposing tokens

The tool SHALL list managed snapshots and inspect saved account metadata without printing raw access, refresh, or ID tokens.

#### Scenario: List saved accounts
- **WHEN** the operator runs `list` or `ls`
- **THEN** the tool shows each managed account with its active marker, auth mode, account identifier, and update timestamp

#### Scenario: Inspect a saved account
- **WHEN** the operator runs `inspect` for an existing managed account
- **THEN** the tool returns stored metadata fields for that account and omits raw token values

### Requirement: Rename and remove managed snapshots safely

The tool SHALL support renaming and removing managed snapshots while protecting the currently active account unless the operator explicitly overrides that protection.

#### Scenario: Rename a managed snapshot
- **WHEN** the operator renames an existing account to an unused valid name
- **THEN** the tool renames the snapshot file and updates the registry metadata to use the new name

#### Scenario: Block removing the active account by default
- **WHEN** the operator attempts to remove the active managed account without `--force-current`
- **THEN** the tool rejects the removal and preserves the managed snapshot and active registry entry

### Requirement: Report local snapshot store health

The tool SHALL provide a `doctor` command that reports whether the managed store, registry, live auth file, and Codex executable state are locally healthy.

#### Scenario: Report a healthy local setup
- **WHEN** the managed store, registry, snapshots, and live auth file are valid and the Codex executable is available
- **THEN** the doctor output reports those checks as healthy and includes the managed snapshot count

#### Scenario: Report invalid local data
- **WHEN** the registry, a managed snapshot, or the live auth file cannot be parsed or validated
- **THEN** the doctor output flags the corresponding health field as invalid instead of hiding the failure
