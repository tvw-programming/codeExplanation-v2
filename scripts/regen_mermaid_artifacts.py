#!/usr/bin/env python3
"""Backfill mermaidLifecycle + architecture.md from checked-in interactive.json.

Uses embedded visualGraph / lifecycleFlows as SoT (no re-extract).
Run from repo root: python3 scripts/regen_mermaid_artifacts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.visual.architecture_docs import write_architecture_markdown
from src.visual.mermaid_export import export_lifecycle_mermaid, export_mermaid


def regen_one(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    graph = payload.get("visualGraph")
    flows = payload.get("lifecycleFlows") or []

    mermaid, m_reason = export_mermaid(graph)
    life, l_reason = export_lifecycle_mermaid(flows)

    payload["mermaid"] = mermaid
    if m_reason:
        payload["mermaidSkipReason"] = m_reason
    else:
        payload.pop("mermaidSkipReason", None)

    payload["mermaidLifecycle"] = life
    if l_reason:
        payload["mermaidLifecycleSkipReason"] = l_reason
    else:
        payload.pop("mermaidLifecycleSkipReason", None)

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # architecture.md needs a record-shaped dict (same fields as payload)
    arch = write_architecture_markdown(payload, path.parent)
    return {
        "path": str(path.relative_to(ROOT)),
        "mermaid": bool(mermaid),
        "lifecycle": bool(life),
        "architecture": bool(arch),
        "m_reason": m_reason,
        "l_reason": l_reason,
    }


def main() -> int:
    visuals = ROOT / "visuals"
    paths = sorted(visuals.rglob("interactive.json"))
    if not paths:
        print("no interactive.json under visuals/")
        return 0
    written = 0
    for p in paths:
        summary = regen_one(p)
        written += 1
        flags = []
        if summary["mermaid"]:
            flags.append("mermaid")
        if summary["lifecycle"]:
            flags.append("lifecycle")
        if summary["architecture"]:
            flags.append("architecture.md")
        print(f"{summary['path']}: {', '.join(flags) or 'updated (skips only)'}")
    print(f"regen_mermaid_artifacts: {written} interactive.json processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
