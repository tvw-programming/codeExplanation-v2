#!/usr/bin/env bash
# run-local.sh — run the whole codeExplanation-v2 project locally with
# one command and the default configuration. Does four things, in order:
#
#   1. Run the Python backend pipeline (detect -> chunk -> extract ->
#      narrate -> render) against whatever repo pipeline.config.yaml
#      points at (creating it from pipeline.config.example.yaml first
#      if you don't have one yet).
#   2. Install render-app's node modules (npm install), if not already
#      installed.
#   3. Start a local web server and leave it running, so you can open
#      the documentation (the MUI tree viewer over /documentation) in
#      a browser at http://localhost:4173/docs-viewer/
#   4. Render the pipeline's output to a real video file at a fixed
#      path: ./output/video.mp4
#
# Usage:
#   ./run-local.sh                  # all four steps
#   ./run-local.sh --no-render      # steps 1-3 only; skips TTS/video,
#                                     # so step 4 is skipped too
#   ./run-local.sh --backend-only   # step 1 only
#   ./run-local.sh --skip-docs-server   # steps 1, 2, 4 — no web server
#   ./run-local.sh --stop-docs-server   # stop a server from a previous run
#   ./run-local.sh --help
#
# Fixed locations:
#   Video:          ./output/video.mp4
#   Docs server:    http://localhost:4173/docs-viewer/  (port via $DOCS_PORT)
#   Backend data:   ./.local-run/  (resolved source clone + pilot report)
#
# Prerequisites this script does NOT install for you: python3, node/npm,
# and (for real rendered audio/video) espeak-ng and ffmpeg/ffprobe.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

RUN_BACKEND=1
RUN_NPM_INSTALL=1
RUN_DOCS_SERVER=1
RUN_VIDEO_RENDER=1
RENDER_FLAG=""
RENDER_ENABLED=1

DOCS_PORT="${DOCS_PORT:-4173}"
LOCAL_RUN_DIR="$PROJECT_ROOT/.local-run"
DOCS_PID_FILE="$LOCAL_RUN_DIR/docs-server.pid"
DOCS_LOG_FILE="$LOCAL_RUN_DIR/docs-server.log"
OUTPUT_DIR="$PROJECT_ROOT/output"
OUTPUT_VIDEO="$OUTPUT_DIR/video.mp4"

for arg in "$@"; do
  case "$arg" in
    --no-render)
      RENDER_FLAG="--no-render"
      RENDER_ENABLED=0
      RUN_VIDEO_RENDER=0
      ;;
    --backend-only)
      RUN_NPM_INSTALL=0
      RUN_DOCS_SERVER=0
      RUN_VIDEO_RENDER=0
      ;;
    --skip-docs-server) RUN_DOCS_SERVER=0 ;;
    --stop-docs-server)
      stop_docs_server() {
        if [ -f "$DOCS_PID_FILE" ] && kill -0 "$(cat "$DOCS_PID_FILE")" 2>/dev/null; then
          kill "$(cat "$DOCS_PID_FILE")"
          rm -f "$DOCS_PID_FILE"
          echo "Stopped the documentation server."
        else
          echo "No documentation server is running (per $DOCS_PID_FILE)."
        fi
      }
      stop_docs_server
      exit 0
      ;;
    -h|--help)
      sed -n '2,27p' "$0"
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
# Preflight: catch missing native tools with a clear, OS-specific
# fix instead of letting them fail silently deep inside the pipeline
# (e.g. without espeak-ng, TTS synthesis fails for every chunk, and
# all run_backend_pilot.py reports is "No successfully-rendered
# chunk to stage" — see src/render/tts.py).
# ---------------------------------------------------------------------
check_render_prerequisites() {
  local missing=0

  if ! command -v espeak-ng >/dev/null 2>&1; then
    missing=1
    echo "espeak-ng was not found on PATH — it's required for narration audio" >&2
    echo "(see src/render/tts.py). Install it, then re-run:" >&2
    case "$(uname -s)" in
      Darwin) echo "    brew install espeak-ng" >&2 ;;
      Linux)  echo "    sudo apt-get install espeak-ng   # Debian/Ubuntu" >&2
              echo "    sudo dnf install espeak-ng       # Fedora" >&2 ;;
      *)      echo "    See https://github.com/espeak-ng/espeak-ng for your platform." >&2 ;;
    esac
  fi

  if ! command -v ffprobe >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
    missing=1
    echo "ffmpeg/ffprobe was not found on PATH — required to measure narration" >&2
    echo "audio duration and to finish the video render. Install it, then re-run:" >&2
    case "$(uname -s)" in
      Darwin) echo "    brew install ffmpeg" >&2 ;;
      Linux)  echo "    sudo apt-get install ffmpeg      # Debian/Ubuntu" >&2
              echo "    sudo dnf install ffmpeg          # Fedora" >&2 ;;
      *)      echo "    See https://ffmpeg.org/download.html for your platform." >&2 ;;
    esac
  fi

  if [ "$missing" = "1" ]; then
    echo "" >&2
    echo "Run with --no-render to skip TTS/video and just exercise the rest" >&2
    echo "of the pipeline, or install the tool(s) above and re-run." >&2
    exit 1
  fi
}

# ---------------------------------------------------------------------
# 1) Python backend pipeline, default configuration
# ---------------------------------------------------------------------
run_backend() {
  log "[1/4] Backend: setting up Python environment"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found on PATH." >&2
    exit 1
  fi

  if [ "$RENDER_ENABLED" = "1" ]; then
    check_render_prerequisites
  fi

  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt

  if [ ! -f pipeline.config.yaml ]; then
    echo "No pipeline.config.yaml found — using the default configuration."
    cp pipeline.config.example.yaml pipeline.config.yaml
    echo "Created pipeline.config.yaml from pipeline.config.example.yaml."
    echo "Edit it any time to point the pipeline at a different repo — see"
    echo "documentation/02-configuration.md for every field."
  fi

  log "[1/4] Backend: running the pipeline (detect -> chunk -> extract -> narrate -> render)"
  python scripts/run_backend_pilot.py $RENDER_FLAG

  deactivate
}

# ---------------------------------------------------------------------
# 2) Install render-app's node modules
# ---------------------------------------------------------------------
run_npm_install() {
  log "[2/4] Frontend: installing render-app's node modules"

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm (Node.js) is required but was not found on PATH." >&2
    exit 1
  fi

  cd "$PROJECT_ROOT/render-app"
  if [ ! -d node_modules ]; then
    npm install
  else
    echo "node_modules already installed — skipping (delete render-app/node_modules to force a reinstall)."
  fi
  cd "$PROJECT_ROOT"
}

# ---------------------------------------------------------------------
# 3) Start a local server so the documentation is viewable in a browser
# ---------------------------------------------------------------------
run_docs_server() {
  log "[3/4] Docs: building and serving the documentation viewer"

  cd "$PROJECT_ROOT/render-app"
  npm run build:docs
  cd "$PROJECT_ROOT"

  mkdir -p "$LOCAL_RUN_DIR"

  # Stop a server left over from a previous run before starting a new one.
  if [ -f "$DOCS_PID_FILE" ] && kill -0 "$(cat "$DOCS_PID_FILE")" 2>/dev/null; then
    kill "$(cat "$DOCS_PID_FILE")"
    sleep 0.3
  fi

  ( cd render-app/public && exec python3 -m http.server "$DOCS_PORT" ) \
    > "$DOCS_LOG_FILE" 2>&1 &
  echo $! > "$DOCS_PID_FILE"
  sleep 0.5

  if kill -0 "$(cat "$DOCS_PID_FILE")" 2>/dev/null; then
    echo "Documentation server running at: http://localhost:$DOCS_PORT/docs-viewer/"
    echo "(left running in the background — stop it with: ./run-local.sh --stop-docs-server)"
  else
    echo "Documentation server failed to start — see $DOCS_LOG_FILE" >&2
  fi
}

# ---------------------------------------------------------------------
# 4) Render the pipeline's output to a real video file at a fixed path
# ---------------------------------------------------------------------
run_video_render() {
  log "[4/4] Video: rendering output/video.mp4"

  if [ ! -f render-app/public/sample-chunk/bundle.json ]; then
    echo "No rendered chunk is staged at render-app/public/sample-chunk/ —" >&2
    echo "run the backend step first without --no-render so there is" >&2
    echo "something to render." >&2
    exit 1
  fi

  mkdir -p "$OUTPUT_DIR"

  cd "$PROJECT_ROOT/render-app"

  # In some sandboxed Linux CI/dev environments, Remotion's own
  # headless-Chromium download is blocked by the network allowlist
  # (see documentation/09-phase6-rendering.md) — fall back to a
  # Playwright Chromium already installed there instead. This glob
  # only ever matches that one specific sandbox path, so on macOS/a
  # normal Linux machine it stays empty and Remotion manages its own
  # bundled browser as usual.
  BROWSER_EXECUTABLE=""
  for candidate in /opt/pw-browsers/chromium-*/chrome-linux64/chrome; do
    if [ -x "$candidate" ]; then
      BROWSER_EXECUTABLE="$candidate"
      break
    fi
  done

  # Default to a single concurrent browser tab. Remotion's headless
  # Chromium can crash mid-render ("Target closed" — see
  # https://remotion.dev/docs/target-closed) when several tabs compete
  # for memory/CPU; rendering one frame batch at a time is slower but
  # far more reliable on a laptop. Override with REMOTION_CONCURRENCY.
  RENDER_CONCURRENCY="${REMOTION_CONCURRENCY:-1}"

  RENDER_ARGS=(CodeExplainerChunk "$OUTPUT_VIDEO" "--concurrency=$RENDER_CONCURRENCY")
  if [ -n "$BROWSER_EXECUTABLE" ]; then
    RENDER_ARGS+=(--browser-executable="$BROWSER_EXECUTABLE")
  fi
  if [ "${RUN_LOCAL_VERBOSE:-0}" = "1" ]; then
    RENDER_ARGS+=(--log=verbose)
  fi

  if ! npx remotion render "${RENDER_ARGS[@]}"; then
    cd "$PROJECT_ROOT"
    echo "" >&2
    echo "Video render failed. This is almost always Remotion's headless" >&2
    echo "Chromium crashing mid-render (see https://remotion.dev/docs/target-closed)," >&2
    echo "not a bug in the pipeline's output. Things to try:" >&2
    echo "  1. Verify/reinstall Remotion's own browser:" >&2
    echo "       cd render-app && npx remotion browser ensure" >&2
    echo "  2. Re-run with full Chromium logs to see what actually happened:" >&2
    echo "       RUN_LOCAL_VERBOSE=1 ./run-local.sh --skip-docs-server" >&2
    echo "  3. If it's a low-memory machine, close other apps and retry — the" >&2
    echo "     render already uses --concurrency=1 to use as little as possible." >&2
    exit 1
  fi
  cd "$PROJECT_ROOT"

  echo "Video written to: $OUTPUT_VIDEO"
}

if [ "$RUN_BACKEND" = "1" ]; then run_backend; fi
if [ "$RUN_NPM_INSTALL" = "1" ]; then run_npm_install; fi
if [ "$RUN_DOCS_SERVER" = "1" ]; then run_docs_server; fi
if [ "$RUN_VIDEO_RENDER" = "1" ]; then run_video_render; fi

log "Done."
if [ "$RUN_DOCS_SERVER" = "1" ]; then echo "Documentation: http://localhost:$DOCS_PORT/docs-viewer/"; fi
if [ "$RUN_VIDEO_RENDER" = "1" ]; then echo "Video:         $OUTPUT_VIDEO"; fi

exit 0
