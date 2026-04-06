## Context

Account transfer extends the local-only snapshot manager with a deliberate cross-machine handoff workflow. The implementation adds an encrypted single-file archive format, interactive selection prompts, and import conflict planning while preserving the core rule that local live auth state is switched only by `use`.

The transfer workflow spans multiple modules: CLI argument handling, prompt orchestration, passphrase-based encryption, archive validation, and batch writes into the managed snapshot store. That cross-cutting behavior is why the retroactive release record needs an explicit design artifact.

## Goals / Non-Goals

**Goals:**
- Define a passphrase-protected archive format for exporting selected managed accounts.
- Define interactive batch selection for both export and import workflows.
- Define explicit conflict handling for importing accounts into an existing local store.
- Preserve the local switching model by preventing imports from changing the current live auth automatically.

**Non-Goals:**
- Provide automatic cloud sync or multi-machine coordination.
- Support fully non-interactive account selection for transfer workflows.
- Treat an imported archive as a command to activate or verify an account automatically.

## Decisions

### Use a dedicated encrypted transfer archive

Transfers use a dedicated archive format instead of raw snapshot files so the tool can package multiple accounts, include format metadata, and apply authenticated encryption over the payload. This keeps the transfer concern separate from the internal on-disk snapshot layout.

### Keep account selection interactive

Both export and import require interactive account selection. The CLI may accept `--passphrase-file` to avoid typing a passphrase manually, but it still requires a TTY for selecting which accounts are exported or imported.

### Resolve import conflicts before writing files

Imports build a plan before writing snapshots. When archive entries collide with existing local names, the operator chooses `skip`, `overwrite`, or `rename` per conflict. This avoids partially surprising writes and keeps the result explicit.

### Do not let import mutate the current live session

Import only writes managed snapshot files and registry metadata. It does not overwrite `~/.codex/auth.json`, does not change the active managed account, and does not run post-import verification. Switching remains a separate, explicit action.

## Risks / Trade-offs

- [Credential sensitivity] Even encrypted bundles remain sensitive because the archive contains authentication material. Mitigation: keep the archive passphrase-protected and document that archives must still be handled as secrets.
- [Interactive-only UX] Operators cannot script account selection non-interactively. Mitigation: keep passphrase-file support for automation-adjacent use cases while preserving explicit selection prompts.
- [Conflict prompt fatigue] Large imports with many name collisions require repeated decisions. Mitigation: keep the decision set small and predictable: skip, overwrite, or rename.

## Migration Plan

Archive this completed retroactive change with spec sync enabled after the baseline bootstrap change has already seeded the main specs.

## Open Questions

None.
