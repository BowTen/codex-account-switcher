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

本仓库以公开方式维护，欢迎通过议题或合并请求提交问题、改进建议和实现修复。
