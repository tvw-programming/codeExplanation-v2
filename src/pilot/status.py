"""Live pipeline status, published for the viewer frontend.

A full run takes many minutes. The viewer (``frontend/``) starts before
the pipeline does and polls ``render-app/public/status.json`` so it can
say which phase is running and which stack videos are watchable yet,
instead of showing an empty page until everything finishes.

The file is rewritten in place many times during a run while a browser
is reading it, so every write goes through a temp file and
``os.replace`` — a reader either sees the previous complete document or
the next one, never half of either.

Nothing here is required for the pipeline to work: a failure to publish
status is swallowed, because a broken progress banner must not break a
render.

Also usable from a shell, which is how run-local.sh reports the stages
that happen outside Python (the Remotion renders):

    python -m src.pilot.status --phase rendering --label "Rendering video"
    python -m src.pilot.status --video-ready go
    python -m src.pilot.status --error "render failed for react"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATUS_PATH = REPO_ROOT / "render-app" / "public" / "status.json"

#: Human wording for each phase the frontend may see. Keys match
#: src.pilot.run_pilot.PHASES plus the stages run-local.sh drives.
PHASE_LABELS = {
    "starting": "Starting up",
    "detect": "Detecting the project type",
    "extract": "Extracting code into chunks",
    "validate": "Validating chunk records",
    "narrate": "Writing the narration",
    "render": "Synthesising narration audio",
    "staging": "Staging chunks for the video",
    "indexing": "Indexing where each file appears",
    "rendering": "Rendering the stack videos",
    "done": "Finished",
    "failed": "Failed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class StatusWriter:
    """Reads, mutates and atomically rewrites status.json."""

    def __init__(self, path: Path | str = DEFAULT_STATUS_PATH):
        self.path = Path(path)

    # ---- io ----

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, state: dict) -> None:
        """Atomic replace, so a polling browser never reads a half file."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".status-",
                suffix=".json",
                delete=False,
            ) as handle:
                json.dump(state, handle, indent=2)
                handle.write("\n")
                temp_name = handle.name
            os.replace(temp_name, self.path)
        except OSError:
            # Publishing progress is never worth failing a run over.
            pass

    # ---- mutations ----

    def start(self, source: str | None = None, render: bool = True) -> dict:
        """Begins a fresh run, discarding a previous run's state."""
        state = {
            "schemaVersion": SCHEMA_VERSION,
            "phase": "starting",
            "phaseLabel": PHASE_LABELS["starting"],
            "startedAt": _now(),
            "updatedAt": _now(),
            "source": source,
            "renderEnabled": render,
            "chunksTotal": 0,
            "chunksRendered": 0,
            "stacks": [],
            "videos": {},
            "done": False,
            "error": None,
        }
        self._write(state)
        return state

    def update(self, **fields) -> dict:
        state = self.read()
        if not state:
            state = self.start()
        state.update(fields)
        if "phase" in fields and "phaseLabel" not in fields:
            state["phaseLabel"] = PHASE_LABELS.get(fields["phase"], fields["phase"])
        state["updatedAt"] = _now()
        self._write(state)
        return state

    def on_progress(self, event: dict) -> dict:
        """Callback shape expected by run_pilot(progress=...)."""
        fields = {
            "phase": event.get("phase", "starting"),
            "chunksTotal": event.get("chunksTotal", 0),
            "chunksRendered": event.get("chunksRendered", 0),
        }
        return self.update(**fields)

    def set_stacks(self, videos: dict[str, dict]) -> dict:
        """Declares the per-stack videos this run will produce.

        `videos` maps stack name -> {"composition", "file", "ready"}.
        Existing `ready` flags are preserved so re-declaring the set
        mid-run does not mark finished videos unwatchable again.
        """
        state = self.read()
        existing = state.get("videos") or {}
        merged: dict[str, dict] = {}
        for stack, entry in videos.items():
            previous = existing.get(stack) or {}
            merged[stack] = {**entry, "ready": entry.get("ready", previous.get("ready", False))}
        return self.update(stacks=sorted(merged), videos=merged)

    def mark_video_ready(self, stack: str, file_name: str | None = None) -> dict:
        state = self.read()
        videos = dict(state.get("videos") or {})
        entry = dict(videos.get(stack) or {})
        entry.setdefault("composition", f"StackVideo-{stack}")
        entry["file"] = file_name or entry.get("file") or f"video-{stack}.mp4"
        entry["ready"] = True
        videos[stack] = entry
        return self.update(videos=videos, stacks=sorted(videos))

    def finish(self) -> dict:
        return self.update(phase="done", done=True)

    def fail(self, message: str) -> dict:
        return self.update(phase="failed", done=True, error=message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update the pipeline status file.")
    parser.add_argument("--path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--phase")
    parser.add_argument("--label")
    parser.add_argument("--video-ready", metavar="STACK")
    parser.add_argument("--video-file", metavar="FILENAME")
    parser.add_argument("--error")
    parser.add_argument("--done", action="store_true")
    args = parser.parse_args(argv)

    writer = StatusWriter(args.path)
    if args.phase:
        fields = {"phase": args.phase}
        if args.label:
            fields["phaseLabel"] = args.label
        writer.update(**fields)
    if args.video_ready:
        writer.mark_video_ready(args.video_ready, args.video_file)
    if args.error:
        writer.fail(args.error)
    elif args.done:
        writer.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
