# Public README And Repo Release Design

**Date:** 2026-04-04

**Goal:** Update this repository for public release by rewriting the README in Chinese for open-source developers, aligning repository metadata with the new positioning, and making the GitHub repository public.

## Scope

This design covers a documentation and repository-release pass only.

Included:
- Rewrite `README.md` in Chinese.
- Reposition the README for public developers rather than private personal use.
- Update the GitHub repository description to a Chinese public-facing summary.
- Change the repository visibility from private to public.
- Adjust lightweight project-file tests so the README structure and published install path remain verified.

Excluded:
- Any CLI feature changes.
- Packaging or distribution changes beyond documentation.
- New docs pages outside the README.
- CI workflow changes unless required by the README/test alignment.

## Target Audience

The public README should be written for developers who:
- already use Codex locally;
- want to keep multiple local login states;
- need a small CLI to save, inspect, and switch `auth.json` snapshots safely.

The document should assume basic command-line familiarity and should not explain generic Git, Python, or GitHub concepts in depth.

## README Positioning

The README should be pure Chinese and present the project as a practical open-source utility.

The tone should be:
- direct;
- concise;
- developer-oriented;
- explicit about security boundaries.

The README should avoid:
- internal/private wording;
- English-first phrasing;
- vague marketing language;
- overstating security guarantees.

## README Structure

The README should contain these sections, in this order:

1. Project title
2. Short Chinese summary
3. `## 适用场景`
4. `## 功能概览`
5. `## 安全说明`
6. `## 安装`
7. `## 命令示例`
8. `## 开发与测试`
9. `## 开源说明`

Content expectations:
- The summary should explain that `codex-auth` manages multiple local Codex `auth.json` snapshots.
- `适用场景` should explain when this tool is useful.
- `功能概览` should summarize save/switch/list/inspect/doctor capabilities.
- `安全说明` should state that credentials remain local, are not encrypted in the first release, and must not be committed.
- `安装` should include the concrete public GitHub install command using the real public repo URL:
  `uv tool install git+https://github.com/BowTen/codex-account-switcher.git`
- `命令示例` should show realistic command usage, including a non-interactive remove example with `--yes`.
- `开发与测试` should keep the local `uv` development path.
- `开源说明` should state the repo is public and welcomes issue/PR based contributions in concise Chinese.

## Repository Metadata

The GitHub repository description should be updated to a concise Chinese sentence:

`用于管理多套本地 Codex auth.json 登录快照的命令行工具`

The repository visibility should be changed from `PRIVATE` to `PUBLIC`.

No other GitHub settings are in scope for this pass.

## Testing

Project-file tests should be updated to verify:
- the README contains the expected Chinese section headings;
- the README contains the public GitHub install command;
- the README still references `codex-auth`;
- `pyproject.toml` still declares the README metadata.

This release pass does not require behavior tests because no CLI behavior changes are planned.
