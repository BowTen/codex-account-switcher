from pathlib import Path


def test_readme_mentions_uv_install_and_codex_auth() -> None:
    text = Path("README.md").read_text()
    assert "uv tool install" in text
    assert "codex-auth" in text


def test_ci_workflow_exists() -> None:
    workflow = Path(".github/workflows/ci.yml")
    assert workflow.exists()
