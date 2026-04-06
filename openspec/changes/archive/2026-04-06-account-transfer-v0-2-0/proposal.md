## Why

The project now includes encrypted account transfer workflows, but OpenSpec was added after that release work had already shipped. This retroactive change records the transfer capability so future changes can extend it from an explicit contract.

## What Changes

- Record the export workflow for packaging selected saved accounts into a passphrase-protected transfer archive.
- Record the import workflow for selectively restoring accounts from a transfer archive.
- Record the interactive selection and conflict-resolution rules that govern transfer operations.

## Capabilities

### New Capabilities
- `account-transfer`: Exporting and importing managed account snapshots through encrypted transfer bundles.

### Modified Capabilities

None.

## Impact

- Extends the main OpenSpec set with transfer requirements on top of the baseline account management capabilities.
- Documents behavior implemented in `src/codex_auth/cli.py`, `src/codex_auth/service.py`, `src/codex_auth/store.py`, `src/codex_auth/prompts.py`, `src/codex_auth/transfer.py`, and `src/codex_auth/errors.py`.
- Captures the shipped release represented by the current `v0.2.0` version line.
