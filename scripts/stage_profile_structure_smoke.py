#!/usr/bin/env python3
"""Stage ProfilePage structure smoke chunk for StackVideo-react preview checks.

Writes render-app/public/chunks/react/alumni-06f407dc/ from visuals fixture +
measured clip TTS. Not invoked by CI — local / agent verification only.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.phase_style import resolve_phase_style, stack_manifest_payload  # noqa: E402
from src.render.render_pipeline import _build_visual_clip_fields  # noqa: E402

CHUNK_ID = "alumni-06f407dc"
STACK = "react"
FIXTURE = REPO_ROOT / "visuals" / "react" / CHUNK_ID
CHUNK_DIR = REPO_ROOT / "render-app" / "public" / "chunks" / STACK / CHUNK_ID
CHUNKS_ROOT = REPO_ROOT / "render-app" / "public" / "chunks"


def main() -> int:
    graph = json.loads((FIXTURE / "visualGraph.json").read_text(encoding="utf-8"))
    record = {
        "chunkId": CHUNK_ID,
        "filePath": "src/features/alumni/ProfilePage.tsx",
        "stack": STACK,
        "featureName": "ProfilePage",
        "durationMs": 45_000,
        "visualAvailability": {
            "componentTree": "partial",
            "lifecycleFlow": "unavailable",
            "interactiveBreakdown": "partial",
            "reasons": {},
        },
        "visualGraph": graph,
        "lifecycleFlows": [],
        "fileOverview": {
            "fileName": "ProfilePage.tsx",
            "purpose": "Alumni profile editing surface.",
            "filePath": "src/features/alumni/ProfilePage.tsx",
        },
        "cardNarration": {
            "audio": "card.wav",
            "durationMs": 6500,
            "spoken": "ProfilePage.tsx. Alumni profile editing surface.",
            "engine": "smoke",
        },
        "narrationSegments": [],
        "highlightConfig": {"cues": []},
    }

    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    visual = _build_visual_clip_fields(record, CHUNK_DIR)
    record.update(visual)

    # Minimal walkthrough track so the composition advances past structure clips.
    from src.render.audio_assembly import silence_wav

    silence_wav(record["durationMs"], CHUNK_DIR / "narration.wav")
    (CHUNK_DIR / "card.wav").write_bytes((CHUNK_DIR / "narration.wav").read_bytes()[:44])

    src_stub = FIXTURE.parent.parent.parent / "README.md"
    if src_stub.is_file():
        shutil.copyfile(src_stub, CHUNK_DIR / "source.tsx")
    else:
        (CHUNK_DIR / "source.tsx").write_text("// ProfilePage smoke\n", encoding="utf-8")

    (CHUNK_DIR / "bundle.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )

    phase_style = resolve_phase_style({})
    stack_manifest = stack_manifest_payload(STACK, [CHUNK_ID], phase_style)
    (CHUNKS_ROOT / STACK).mkdir(parents=True, exist_ok=True)
    (CHUNKS_ROOT / STACK / "manifest.json").write_text(
        json.dumps(stack_manifest, indent=2) + "\n", encoding="utf-8",
    )
    combined = {
        "chunkIds": [CHUNK_ID],
        "stacks": {STACK: [CHUNK_ID]},
        "phaseStyle": phase_style,
    }
    (CHUNKS_ROOT / "manifest.json").write_text(
        json.dumps(combined, indent=2) + "\n", encoding="utf-8",
    )

    print(f"[smoke] staged {CHUNK_DIR.relative_to(REPO_ROOT)}")
    print(f"[smoke] tree beat0 speechEndMs={record['treeNarration']['beats'][0]['speechEndMs']}")
    print(f"[smoke] breakdown beats={len(record['breakdownNarration']['beats'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())