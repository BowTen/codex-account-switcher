## Context

The repository already contains later functionality, but the project originally started as a local account snapshot and switching CLI. OpenSpec was introduced after those capabilities were implemented, so this change establishes a stable baseline that future changes can extend.

The baseline is taken from the pre-transfer mainline behavior: snapshots are stored locally under the managed store, the live Codex auth file remains the source that gets switched, and successful switches are verified with `codex login status`.

## Goals / Non-Goals

**Goals:**
- Capture the original managed snapshot lifecycle as a spec capability.
- Capture the original live account switching and verification behavior as a spec capability.
- Seed main specs that later changes can modify incrementally.

**Non-Goals:**
- Reconstruct an exact historical release artifact or commit-for-commit narrative.
- Introduce transfer, encryption, or cross-machine migration requirements.
- Change any runtime behavior in the application.

## Decisions

### Split the baseline into storage and switching capabilities

The original CLI exposed both account storage workflows and account switching workflows, but they serve different concerns. `account-snapshots` covers persistence, metadata, inspection, deletion, and diagnostics. `account-switching` covers mutation of the live auth file and current-account reporting.

### Treat `doctor` as part of snapshot management

`doctor` reports the health of the managed store, registry, and live auth file. Even though it also inspects the Codex executable, its purpose is to validate the local snapshot environment, so it belongs with snapshot management instead of becoming a separate capability.

### Record the baseline from the pre-transfer mainline, not the retroactive tag

The repository's `v0.1.0` tag was added later and points to a commit that already includes transfer support. The retroactive baseline therefore references the pre-transfer mainline behavior as the authoritative source for the original capability set.

## Risks / Trade-offs

- [Historical drift] The reconstructed baseline may omit minor incidental behavior. Mitigation: keep requirements at the user-visible contract level and avoid overfitting to internal implementation details.
- [Version naming ambiguity] The `v0.1.0` tag does not identify the true pre-transfer code state. Mitigation: document that fact directly in this change instead of pretending the tag is authoritative.

## Migration Plan

Archive this completed retroactive change with spec sync enabled so it seeds `openspec/specs/account-snapshots/` and `openspec/specs/account-switching/`.

## Open Questions

None.
