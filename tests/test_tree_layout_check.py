"""Shell out to the Remotion tree-layout invariant script."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "render-app"


def test_tree_layout_invariants():
    result = subprocess.run(
        ["npx", "--yes", "tsx", "scripts/check-tree-layout.ts"],
        cwd=RENDER,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "ok" in result.stdout
