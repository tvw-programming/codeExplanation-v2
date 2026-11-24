"""Shell out to structure-teaching invariant script."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "render-app"


def test_structure_teaching_invariants():
    result = subprocess.run(
        ["npx", "--yes", "tsx", "scripts/check-structure-teaching.ts"],
        cwd=RENDER,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "ok" in result.stdout