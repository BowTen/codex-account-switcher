## Context

The CLI already stores ChatGPT-backed account snapshots with `access_token`, `refresh_token`, `id_token`, and `account_id`, but it only exposes snapshot management, switching, and transfer workflows. Operators who manage multiple accounts currently have to switch accounts manually or use ad hoc scripts to compare remaining quota, even though the ChatGPT backend exposes structured rate-limit data.

This change crosses multiple modules because it adds a new CLI command, introduces network access for usage and token refresh, and must preserve the existing storage guarantees around local snapshots and the live `~/.codex/auth.json`. The design therefore needs explicit decisions about data source, refresh side effects, deduplication between live and managed accounts, and failure handling for multi-account queries.

## Goals / Non-Goals

**Goals:**
- Add a non-interactive `codex-auth usage [name]` command for named and batch quota inspection.
- Query structured usage data for managed snapshots and the current unmanaged live account without switching accounts.
- Refresh expired or near-expiry ChatGPT OAuth access tokens automatically and persist refreshed credentials consistently.
- Keep batch queries resilient so one failing account does not prevent other results from rendering.
- Render usage in a human-friendly terminal format that emphasizes remaining 5-hour and weekly quota.

**Non-Goals:**
- Introduce JSON or machine-readable output in this change.
- Support API-key-based usage queries.
- Modify account switching, import/export, or snapshot creation semantics.
- Persist the current unmanaged live account into the managed registry automatically.

## Decisions

### Use the ChatGPT usage endpoint instead of parsing `codex login status`

The command will call `GET https://chatgpt.com/backend-api/wham/usage` with the stored ChatGPT OAuth access token and `chatgpt-account-id` header. This was chosen because current local testing showed that `codex login status` may not emit rate-limit lines at all, while the backend endpoint returns structured JSON with primary and secondary windows.

Alternatives considered:
- Parse `codex login status` output. Rejected because the output is optional, text-only, and unsuitable for stable automated behavior.
- Switch accounts and query usage from the live session only. Rejected because it introduces unnecessary side effects and slows batch queries.

### Keep HTTP logic in focused modules and reuse existing store semantics

The implementation will add one module for token refresh and one module for usage API access. The service layer will own target selection, deduplication, and persistence decisions, while the store will continue to own atomic writes to snapshots, registry metadata, and the live auth file.

Alternatives considered:
- Put refresh and HTTP code directly in `service.py`. Rejected because it would mix networking, selection, and persistence concerns in one file.
- Add a new third-party HTTP dependency. Rejected because stdlib networking is sufficient for this narrow request flow and keeps the runtime surface smaller.

### Treat live unmanaged auth as a separate query target

Bare `usage` will query all managed snapshots and will also query the current live `~/.codex/auth.json` when it does not match any saved managed snapshot identity. The service layer will model this as a first-class query target rather than trying to force it into registry metadata.

Alternatives considered:
- Query only managed accounts. Rejected because the user explicitly wants the current unmanaged session included.
- Auto-save unmanaged live auth before querying. Rejected because it mutates local state outside the usage command's scope.

### Persist refresh results only for the queried account and matching live auth

When an account refresh occurs, the command will overwrite the queried managed snapshot if one exists. It will also update `~/.codex/auth.json` only when the refreshed target matches the current live account. This keeps refresh persistence aligned with the account actually used for the request and avoids unrelated state churn.

Alternatives considered:
- Refresh in memory without writing changes. Rejected because repeated queries would redo the same work and leave stored credentials stale.
- Always rewrite the live auth file after any refresh. Rejected because querying a non-current managed account must not silently change the active session.

### Render remaining quota, not used quota

The output will compute `remaining = max(0, 100 - used_percent)` and display that remaining percentage alongside a fixed-width text progress bar and localized reset time. This matches the operator's primary question: how much room is left before the next reset.

Alternatives considered:
- Show only raw `used_percent`. Rejected because it is less intuitive when scanning many accounts.
- Show only timestamps and no progress bars. Rejected because the user explicitly requested a human-friendly format similar to the existing quota bar examples.

## Risks / Trade-offs

- [ChatGPT backend contract may change] → Keep the API client narrow, validate required fields defensively, and degrade to per-account errors instead of aborting the batch.
- [Refresh requires a built-in OAuth client ID] → Limit its use to the existing refresh flow, isolate it in one module, and document that this command only supports ChatGPT-backed accounts.
- [Network failures could make batch output noisy] → Report concise per-account errors and continue rendering successful accounts.
- [Refresh persistence could accidentally rewrite the wrong file] → Gate live auth updates on identity matching and keep all writes inside existing atomic store helpers.

## Migration Plan

No data migration is required. Existing snapshots already contain the ChatGPT OAuth fields needed for usage queries and refresh. The rollout is:

1. Add usage and refresh modules plus focused tests.
2. Add service-layer target selection and refresh persistence.
3. Add CLI rendering and README documentation.
4. Validate with focused usage tests and the full pytest suite.

Rollback is straightforward: remove the `usage` command and new helper modules without changing stored snapshot format.

## Open Questions

None. The data source, refresh behavior, live-account inclusion, and output style were all resolved during requirement discussion.
