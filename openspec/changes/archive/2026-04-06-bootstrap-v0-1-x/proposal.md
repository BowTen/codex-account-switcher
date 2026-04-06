## Why

OpenSpec was initialized after the project had already shipped core account snapshot and switching behavior. This retroactive change records that baseline so future changes can modify explicit requirements instead of relying on code archaeology.

## What Changes

- Record the pre-transfer baseline for saving, listing, inspecting, renaming, and removing managed account snapshots.
- Record the baseline behavior for switching the live `~/.codex/auth.json` between saved accounts.
- Establish the first main OpenSpec capabilities for this project from the original account-switching workflow.

## Capabilities

### New Capabilities
- `account-snapshots`: Managing named local Codex auth snapshots and related store health checks.
- `account-switching`: Switching the live auth state between managed snapshots and reporting the current live state.

### Modified Capabilities

None.

## Impact

- Seeds the initial OpenSpec main specs for the project.
- Documents behavior implemented in `src/codex_auth/cli.py`, `src/codex_auth/service.py`, `src/codex_auth/store.py`, and `src/codex_auth/validators.py`.
- Retroactively records the pre-transfer baseline from the mainline history rather than the later-added `v0.1.0` tag.
