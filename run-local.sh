#!/usr/bin/env bash
# run-local.sh — run the whole codeExplanation-v2 project locally with
# the default configuration, no arguments, no manual setup, and end
# with a real output.mp4 at the project root.
#
# What it does, in order:
#   1. Backend  — creates/reuses a Python venv, installs requirements.txt,
#      copies pipeline.config.example.yaml -> pipeline.config.yaml if you
#      don't have one yet (so it runs with sane defaults out of the box),
#      then runs the full pipeline (detect -> chunk -> extract -> narrate
#      -> render) against whatever repo pipeline.config.yaml points at,
#      via the Phase 7 pilot runner (scripts/run_backend_pilot.py).
#      One successfully-rendered chunk's audio/highlight-config/source
#      file is staged into render-app/public/sample-chunk/ for the next
#      step. Full report: .local-run/output/pilot_report.json.
#   2. Frontend — installs render-app's npm dependencies if needed,
#      builds the MUI documentation viewer (render-app/public/docs-viewer),
#      then renders that staged chunk straight to ./output.mp4 at the
#      project root via `npx remotion render` — no manual step, no
#      interactive server left running.
#
# Usage:
#   ./run-local.sh                 # default: produces ./output.mp4
#   ./run-local.sh --no-render     # skip TTS/video in the backend step
#                                   # (no output.mp4 can be produced this way)
#   ./run-local.sh --backend-only  # run the backend pilot and exit
#   ./run-local.sh --frontend-only # skip the backend step, just render
#                                   # whatever is already staged
#   ./run-local.sh --studio        # after the backend step, start the
#                                   # interactive Remotion Studio dev
#                                   # server instead of a one-shot render
#
# Prerequisites this script does NOT install for you: python3, node/npm,
# espeak-ng (TTS) and ffmpeg/ffprobe (used by Remotion's own render and
# by the backend's audio-duration measurement). Everything else (the
# venv, pip packages, npm packages, the docs-viewer build) is handled
# automatically.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

RUN_BACKEND=1
RUN_FRONTEND=1
RENDER_FLAG=""
RENDER_ENABLED=1
MODE="render"   # "render" (default, produces output.mp4) or "studio"
OUTPUT_PATH="$PROJECT_ROOT/output.mp4"

for arg in "$@"; do
  case "$arg" in
    --no-render) RENDER_FLAG="--no-render"; RENDER_ENABLED=0 ;;
    --backend-only) RUN_FRONTEND=0 ;;
    --frontend-only) RUN_BACKEND=0 ;;
    --studio) MODE="studio" ;;
    -h|--help)
      sed -n '2,29p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 1
      ;;
  esac
done

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

# ---------------------------------------------------------------------
# Backend: Python pipeline, default configuration
# ---------------------------------------------------------------------
run_backend() {
  log "Backend: setting up Python environment"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found on PATH." >&2
    exit 1
  fi

  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt

  if [ ! -f pipeline.config.yaml ]; then
    log "Backend: no pipeline.config.yaml found — using the default configuration"
    cp pipeline.config.example.yaml pipeline.config.yaml
    echo "Created pipeline.config.yaml from pipeline.config.example.yaml."
    echo "Edit it any time to point the pipeline at a different repo — see"
    echo "documentation/02-configuration.md for every field."
  fi

  log "Backend: running the pipeline (detect -> chunk -> extract -> narrate -> render)"
  python scripts/run_backend_pilot.py $RENDER_FLAG

  deactivate
}

# ---------------------------------------------------------------------
# Frontend: render-app (Remotion — a one-shot video render by default,
# or the interactive Studio dev server with --studio)
# ---------------------------------------------------------------------
run_frontend() {
  log "Frontend: setting up render-app"

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm (Node.js) is required but was not found on PATH." >&2
    exit 1
  fi

  cd "$PROJECT_ROOT/render-app"

  if [ ! -d node_modules ]; then
    npm install
  fi

  log "Frontend: building the documentation viewer"
  npm run build:docs

  if [ "$MODE" = "studio" ]; then
    log "Frontend: starting Remotion Studio (serves the video compositions and the docs viewer)"
    echo "Once it starts, open:"
    echo "  - Remotion Studio:    http://localhost:3000"
    echo "  - Documentation (MUI tree viewer): http://localhost:3000/docs-viewer/"
    echo "Press Ctrl+C to stop."
    npm run dev
    return
  fi

  if [ "$RENDER_ENABLED" = "0" ]; then
    log "Frontend: skipped video render (ran with --no-render, nothing was staged to render)"
    return
  fi

  if [ ! -f public/sample-chunk/bundle.json ]; then
    echo "No rendered chunk is staged at public/sample-chunk/ — run the backend" >&2
    echo "step first (without --no-render) so there is something to render." >&2
    exit 1
  fi

  log "Frontend: rendering output.mp4"
  # Remotion's own headless-Chromium download is blocked by this
  # environment's network allowlist (see documentation/09-phase6-rendering.md
  # and documentation/13-known-gaps-and-roadmap.md) — point it at the
  # Playwright Chromium already installed here instead, the same
  # workaround used when this composition was first proven end to end.
  BROWSER_EXECUTABLE=""
  for candidate in /opt/pw-browsers/chromium-*/chrome-linux64/chrome; do
    if [ -x "$candidate" ]; then
      BROWSER_EXECUTABLE="$candidate"
      break
    fi
  done

  RENDER_ARGS=(CodeExplainerChunk "$OUTPUT_PATH")
  if [ -n "$BROWSER_EXECUTABLE" ]; then
    RENDER_ARGS+=(--browser-executable="$BROWSER_EXECUTABLE")
  fi

  npx remotion render "${RENDER_ARGS[@]}"

  log "Frontend: done"
  echo "Video written to: $OUTPUT_PATH"
}

[ "$RUN_BACKEND" = "1" ] && run_backend
[ "$RUN_FRONTEND" = "1" ] && run_frontend

log "Done."
