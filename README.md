# codex-account-switcher

`codex-auth` 是一个用于管理多套本地 Codex `auth.json` 登录快照的命令行工具，适合需要在同一台机器上保存、切换、检查和迁移多个账号状态的开发者。

## 适用场景

- 你在一台机器上同时使用多个 Codex 账号。
- 你希望保留不同账号的本地登录状态，并在需要时快速切换。
- 你不想每次切换账号都重新执行完整登录流程。

## 功能概览

- 保存当前 `~/.codex/auth.json` 为命名快照。
- 在多个已保存账号之间切换当前登录状态。
- 列出、查看、重命名、删除本地账号快照。
- 查看账号使用额度、重置时间和剩余额度。
- 交互式批量导出/导入（interactive batch export/import）账号快照。
- 通过 `codex login status` 校验切换结果。
- 使用 `doctor` 检查本地存储、权限和 Codex 环境状态。

## 核心功能

- 账号快照管理：把当前登录状态保存成命名快照，并在多个账号之间快速切换。
- 当前状态检查：查看当前 live 账号、已保存快照详情和本地存储健康状态。
- 额度查询：默认批量查询全部账号额度；在交互终端中以实时视图展示查询进度和已完成结果，并在结束后保留一份稳定的最终结果输出；在重定向或管道场景下保持纯文本输出。
- 凭证迁移：通过交互式导入导出在多台机器之间迁移账号快照，同时保持本地明文凭证不进入仓库。

## 安全说明

- 所有登录快照仅保存在当前机器本地，不会自动上传或同步。
- 导出文件是 passphrase-protected credential bundles，但它们仍然是高度敏感的凭证材料。
- 导入和导出都需要交互式终端来完成账号选择。
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

`codex-auth import <file>` 会从指定的导出文件恢复账号快照。

```bash
codex-auth save work
codex-auth ls
codex-auth current
codex-auth inspect work
codex-auth use work
codex-auth usage
codex-auth usage work
codex-auth rename work primary
codex-auth rm work --force-current --yes
codex-auth export
codex-auth import ./codex-auth-export.cae
codex-auth doctor
```

## 开发与测试

```bash
uv run pytest -v
```

## OpenSpec 工作流

本仓库现在使用 OpenSpec 持续维护需求和变更。

- 当前主规格位于 `openspec/specs/`。
- 已完成的历史补录和后续变更归档位于 `openspec/changes/archive/`。
- 新功能、行为变更、以及重要 bugfix 建议先创建一个新的 OpenSpec change，再进入实现。
- 纯文档或纯工具链整理、且不涉及 requirement 变化时，可以在归档时使用 `openspec archive --skip-specs`。

常用流程：

```bash
openspec list --json
openspec new change <name>
openspec status --change <name>
openspec validate <name>
openspec archive <name>
```

## 开源说明

本仓库以公开方式维护，欢迎通过议题或合并请求提交问题、改进建议和实现修复。
