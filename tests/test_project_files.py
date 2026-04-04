from pathlib import Path
import re


def test_readme_mentions_uv_install_and_codex_auth() -> None:
    text = Path("README.md").read_text()
    ordered_markers = [
        "# codex-account-switcher",
        "多套本地 Codex `auth.json`",
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
    assert "uv tool install git+https://github.com/" in text
    assert re.search(r"uv tool install git\+https://github\.com/[^/\s]+/codex-account-switcher\.git", text)
    assert "codex-auth" in text
    assert "仅保存在当前机器本地" in text
    assert "首个公开版本不提供额外加密" in text
    assert "不应提交任何真实的 `auth.json`" in text


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
