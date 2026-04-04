# Public README And Repo Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the repository README in Chinese for public developers, align lightweight documentation tests with the new public copy, and publish the GitHub repository with Chinese metadata.

**Architecture:** Keep this release pass minimal and documentation-first. Lock the new public-facing README structure with project-file tests, then replace the current English README with the approved Chinese content, and finally update GitHub repository metadata and visibility through `gh` with explicit verification commands.

**Tech Stack:** Markdown, Python 3.12, `uv`, `pytest`, GitHub CLI

---

## File Structure

- Modify: `README.md`
  Replace the current English private/internal copy with the Chinese public-facing README.
- Modify: `tests/test_project_files.py`
  Update the lightweight file assertions so they validate the new Chinese README structure and public install path.
- Check only: `pyproject.toml`
  Keep the existing `readme = "README.md"` metadata intact and verify it in tests.
- Operational change: GitHub repository `BowTen/codex-account-switcher`
  Update the repository description and change visibility from private to public with `gh`.

### Task 1: Rewrite The README And Lock It With Tests

**Files:**
- Modify: `tests/test_project_files.py`
- Modify: `README.md`
- Check: `pyproject.toml`

- [ ] **Step 1: Write the failing README structure test**

```python
from pathlib import Path


def test_readme_mentions_public_chinese_sections_and_install_path() -> None:
    text = Path("README.md").read_text()
    assert "## 适用场景" in text
    assert "## 功能概览" in text
    assert "## 安全说明" in text
    assert "## 安装" in text
    assert "## 命令示例" in text
    assert "## 开发与测试" in text
    assert "## 开源说明" in text
    assert "uv tool install git+https://github.com/BowTen/codex-account-switcher.git" in text
    assert "codex-auth" in text
```

Replace the existing README-heading assertions in `tests/test_project_files.py` with the Chinese headings above. Keep the existing CI workflow assertions and the `pyproject.toml` README metadata assertion.

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/test_project_files.py -v`
Expected: FAIL because the current `README.md` still contains English headings such as `## Safety Model`, `## Install`, and `## Development`.

- [ ] **Step 3: Rewrite `README.md` in Chinese with the approved public structure**

Replace the file content with:

```markdown
# codex-account-switcher

`codex-auth` 是一个用于管理多套本地 Codex `auth.json` 登录快照的命令行工具，适合需要在同一台机器上快速切换不同账号状态的开发者。

## 适用场景

- 你在一台机器上同时使用多个 Codex 账号。
- 你希望保留不同账号的本地登录状态，并在需要时快速切换。
- 你不想每次切换账号都重新执行完整登录流程。

## 功能概览

- 保存当前 `~/.codex/auth.json` 为命名快照。
- 在多个已保存账号之间切换当前登录状态。
- 列出、查看、重命名、删除本地账号快照。
- 通过 `codex login status` 校验切换结果。
- 使用 `doctor` 检查本地存储、权限和 Codex 环境状态。

## 安全说明

- 所有登录快照仅保存在当前机器本地，不会自动上传或同步。
- 首个公开版本不提供额外加密，账号快照本质上仍然是本地凭证文件。
- 工具默认不会打印 `access_token`、`refresh_token` 或 `id_token`。
- 仓库中不应提交任何真实的 `auth.json` 或其他凭证文件。

## 安装

直接从 GitHub 安装：

```bash
uv tool install git+https://github.com/BowTen/codex-account-switcher.git
```

本地开发安装：

```bash
uv sync --dev
uv run codex-auth --help
```

## 命令示例

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

## 开发与测试

```bash
uv run pytest -v
```

## 开源说明

本仓库以公开方式维护，欢迎通过 Issue 或 Pull Request 提交问题、改进建议和实现修复。
```

- [ ] **Step 4: Run the targeted tests to verify the README and file checks pass**

Run: `uv run pytest tests/test_project_files.py -v`
Expected: PASS with all project-file tests green.

- [ ] **Step 5: Run the full test suite to verify no regression**

Run: `uv run pytest -v`
Expected: PASS with all tests green.

- [ ] **Step 6: Commit the documentation and test changes**

```bash
git add README.md tests/test_project_files.py
git commit -m "docs: publish chinese public readme"
```

### Task 2: Publish The GitHub Repository Metadata

**Files:**
- Operational change only: GitHub repository `BowTen/codex-account-switcher`

- [ ] **Step 1: Verify the current repository visibility and description before changing them**

Run: `gh repo view BowTen/codex-account-switcher --json visibility,description,url`
Expected: `visibility` is `PRIVATE` (or whatever the current state is) and the current description is empty or outdated.

- [ ] **Step 2: Update the repository description in Chinese**

Run:

```bash
gh repo edit BowTen/codex-account-switcher --description "用于管理多套本地 Codex auth.json 登录快照的命令行工具"
```

Expected: command exits successfully with no error output.

- [ ] **Step 3: Change the repository visibility to public**

Run:

```bash
gh repo edit BowTen/codex-account-switcher --visibility public --accept-visibility-change-consequences
```

Expected: command exits successfully with no error output.

- [ ] **Step 4: Verify the repository is now public and the description is correct**

Run: `gh repo view BowTen/codex-account-switcher --json visibility,description,url`
Expected: `visibility` is `PUBLIC` and `description` is `用于管理多套本地 Codex auth.json 登录快照的命令行工具`.

- [ ] **Step 5: Verify the local branch is still clean and tracking the published repo**

Run: `git status --short --branch`
Expected: clean working tree on `master...origin/master` or `master...origin/master [ahead N]` only if the README commit has not been pushed yet.

- [ ] **Step 6: Push the README commit if needed**

Run:

```bash
git push origin master
```

Expected: push succeeds and `origin/master` includes the README/documentation update commit.
