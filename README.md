# codex-account-switcher

Manage multiple local Codex `auth.json` snapshots with a single CLI: `codex-auth`.

## Safety Model

- The tool stores local credential snapshots on the current machine only.
- It does not encrypt tokens in the first release.
- It never prints raw access, refresh, or ID tokens.
- The repository must never contain real credential snapshots.

## Install

For local development:

```bash
uv sync --dev
uv run codex-auth --help
```

After publishing this repository to GitHub, install it on another machine with:

```bash
uv tool install git+https://github.com/OWNER/codex-account-switcher.git
```

Replace `OWNER` with the GitHub account or organization that owns the repository.

## Commands

```bash
codex-auth save work
codex-auth ls
codex-auth current
codex-auth inspect work
codex-auth use work
codex-auth rename work primary
codex-auth rm work --force-current --yes
codex-auth doctor
```

## Development

```bash
uv run pytest -v
```
