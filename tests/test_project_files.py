from pathlib import Path


def test_readme_mentions_uv_install_and_codex_auth() -> None:
    text = Path("README.md").read_text()
    assert "## Safety Model" in text
    assert "## Install" in text
    assert "## Commands" in text
    assert "## Development" in text
    assert "uv tool install git+https://github.com/OWNER/codex-account-switcher.git" in text
    assert "codex-auth rm work --force-current --yes" in text
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
