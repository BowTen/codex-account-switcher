import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_module_help_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codex_auth", "--help"],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "codex-auth" in result.stdout
