# account-switching Specification

## Purpose
TBD - created by archiving change bootstrap-v0-1-x. Update Purpose after archive.
## Requirements
### Requirement: Switch the live auth file to a saved account

The tool SHALL replace the live `~/.codex/auth.json` with the selected managed snapshot when the operator runs `use` for an existing account.

#### Scenario: Switch to another managed account
- **WHEN** the operator runs `use` for an existing managed account
- **THEN** the tool writes that snapshot into the live auth path and records the selected account as the active managed account

#### Scenario: Preserve the current managed account before switching away
- **WHEN** the current live auth matches the currently active managed account and the operator switches to another managed account
- **THEN** the tool refreshes the stored snapshot for the current active account before writing the new live auth state

### Requirement: Report the current live account state

The tool SHALL report whether the current live auth file corresponds to a managed account or an unmanaged account state.

#### Scenario: Report a managed current account
- **WHEN** the live auth file matches the active managed account
- **THEN** the `current` command reports the managed account metadata with `managed_state` set to `managed`

#### Scenario: Report an unmanaged current account
- **WHEN** a live auth file exists but does not correspond to a managed active account
- **THEN** the `current` command reports the live auth summary with `managed_state` set to `unmanaged`

### Requirement: Verify switch outcomes without undoing the switch

The tool SHALL run `codex login status` after a switch and record verification metadata when the verification succeeds.

#### Scenario: Verification succeeds after a switch
- **WHEN** the switch completes and `codex login status` succeeds
- **THEN** the tool records the selected account's verification timestamp and reports a successful verification result

#### Scenario: Verification fails after a switch
- **WHEN** the switch completes but `codex login status` fails
- **THEN** the tool keeps the selected live auth in place and reports the unsuccessful verification result to the operator

