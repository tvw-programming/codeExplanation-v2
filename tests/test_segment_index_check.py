"""Shell out to the segment-index invariant script.

The index says which seconds of a stack video belong to which source
file. A wrong offset there is worse than a missing one — the viewer
would seek confidently into the wrong file's explanation — so the
invariants run with the rest of the suite.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "render-app"


def test_segment_index_invariants():
    result = subprocess.run(
        ["npx", "--yes", "tsx", "scripts/check-segment-index.ts"],
        cwd=RENDER,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "synthetic layout OK" in result.stdout
