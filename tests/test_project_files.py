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
    assert "interactive batch export/import" in text
    assert "codex-auth export" in text
    assert "codex-auth import <file>" in text
    assert "codex-auth import ./codex-auth-export.cae" in text
    assert "passphrase-protected credential bundles" in text
    assert "高度敏感" in text
    assert "交互式终端" in text
    assert "不会打印 `access_token`、`refresh_token` 或 `id_token`" in text
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
