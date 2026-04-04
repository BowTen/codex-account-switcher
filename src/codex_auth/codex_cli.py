from __future__ import annotations

import shutil
import subprocess
from typing import Mapping

from .models import VerificationResult


def run_login_status(
    executable: str = "codex",
    *,
    env: Mapping[str, str] | None = None,
) -> VerificationResult:
    if shutil.which(executable, path=env.get("PATH") if env else None) is None:
        raise FileNotFoundError(f"Could not find executable: {executable}")

    result = subprocess.run(
        [executable, "login", "status"],
        capture_output=True,
        text=True,
        env=dict(env) if env else None,
    )
    return VerificationResult(
        ok=result.returncode == 0,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
