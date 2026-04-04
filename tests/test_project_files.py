from pathlib import Path


def test_readme_mentions_uv_install_and_codex_auth() -> None:
    text = Path("README.md").read_text()
    ordered_markers = [
        "# codex-account-switcher",
        "`codex-auth` 是一个用于管理多套本地 Codex `auth.json` 登录快照的命令行工具，适合需要在同一台机器上快速切换不同账号状态的开发者。",
        "## 适用场景",
        "## 功能概览",
        "## 安全说明",
        "## 安装",
        "## 命令示例",
        "## 开发与测试",
        "## 开源说明",
    ]
    positions = [text.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)
    assert "uv tool install git+https://github.com/BowTen/codex-account-switcher.git" in text
    assert "codex-auth" in text


def test_ci_workflow_exists() -> None:
    workflow = Path(".github/workflows/ci.yml")
    assert workflow.exists()


def test_ci_workflow_mentions_expected_steps() -> None:
    text = Path(".github/workflows/ci.yml").read_text()
    assert "uv python install 3.12" in text
    assert "uv sync --dev" in text
    assert "uv run pytest -v" in text


def test_pyproject_declares_readme() -> None:
    text = Path("pyproject.toml").read_text()
    assert 'readme = "README.md"' in text
