#!/usr/bin/env bash
# run-local.sh — run the whole codeExplanation-v2 project locally with
# one command and the default configuration. Does five things, in order:
#
#   1. Start the React viewer (frontend/) and leave it running, so you
#      can browse the repo being analysed — one file tree per detected
#      technology — and click a file to watch its explanation. It comes
#      up FIRST, before the pipeline, because a full run takes many
#      minutes; it fills in live as the pipeline publishes progress.
#   2. Run the Python backend pipeline (detect -> chunk -> extract ->
#      narrate -> render) against whatever repo pipeline.config.yaml
#      points at (creating it from pipeline.config.example.yaml first
#      if you don't have one yet).
#   3. Install render-app's node modules and serve the documentation
#      viewer (the MUI tree viewer over /documentation) at
#      http://localhost:4173/docs-viewer/
#   4. Index where each source file appears inside its stack video, so
#      the viewer can seek straight to it.
#   5. Render the pipeline's output to per-stack video files at
#      ./output/video-<stack>.mp4 (e.g. video-react.mp4, video-go.mp4)
#
# Usage:
#   ./run-local.sh                  # all five steps
#   ./run-local.sh --no-render      # steps 1-3 only; skips TTS/video,
#                                     # so steps 4-5 are skipped too
#   ./run-local.sh --backend-only   # step 2 only
#   ./run-local.sh --web-only       # step 1 only — browse what is
#                                     # already on disk, run nothing
#   ./run-local.sh --skip-web           # no React viewer
#   ./run-local.sh --skip-docs-server   # no documentation server
#   ./run-local.sh --preview            # first 120s only, for a fast look
#   ./run-local.sh --preview=30         # first 30s only
#
# --preview renders only the opening stretch of the same video, to
# output/video-<stack>-preview.mp4, so you can check a change in a minute or
# two instead of waiting out the full render. It limits the frame range
# only: the repo is still detected, chunked, extracted, narrated and
# staged in full, and the composition still reports its true duration,
# so a preview shows exactly what the real video's opening looks like.
# Per-stack manifests put chunks that have tree/lifecycle/breakdown
# graphs first, so --preview reaches Go Fiber route trees (and similar)
# instead of spending the window on handler files with no visuals.
# It is never written over output/video.mp4.
#   ./run-local.sh --stop-docs-server   # stop a server from a previous run
#   ./run-local.sh --stop-web           # stop the React viewer
#   ./run-local.sh --help
#
# Fixed locations:
#   Videos:         ./output/video-<stack>.mp4 (one per detected stack)
#   Viewer:         http://localhost:5174/              (React app over
#                   frontend/; port via $WEB_PORT)
#   Static root:    http://localhost:4173/              (docs-server root over
#                   render-app/public; port via $DOCS_PORT)
#   Docs viewer:    http://localhost:4173/docs-viewer/  (same server)
#   Backend data:   ./.local-run/  (resolved source clone + pilot report)
#
# Prerequisites this script does NOT install for you: python3, node/npm,
# and (for real rendered audio/video) espeak-ng and ffmpeg/ffprobe.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

RUN_WEB_SERVER=1
RUN_BACKEND=1
RUN_NPM_INSTALL=1
RUN_DOCS_SERVER=1
RUN_SEGMENT_INDEX=1
RUN_VIDEO_RENDER=1
RENDER_FLAG=""
RENDER_ENABLED=1

DOCS_PORT="${DOCS_PORT:-4173}"
WEB_PORT="${WEB_PORT:-5174}"
# Docs server (python http.server over render-app/public): root = frontend
# static tree; /docs-viewer/ = MUI documentation viewer (from build:docs).
FRONTEND_URL="http://localhost:${DOCS_PORT}/"
DOCS_VIEWER_URL="http://localhost:${DOCS_PORT}/docs-viewer/"
APP_URL="http://localhost:${WEB_PORT}/"
LOCAL_RUN_DIR="$PROJECT_ROOT/.local-run"
DOCS_PID_FILE="$LOCAL_RUN_DIR/docs-server.pid"
DOCS_LOG_FILE="$LOCAL_RUN_DIR/docs-server.log"
WEB_PID_FILE="$LOCAL_RUN_DIR/web-server.pid"
WEB_LOG_FILE="$LOCAL_RUN_DIR/web-server.log"
OUTPUT_DIR="$PROJECT_ROOT/output"
OUTPUT_VIDEO="$OUTPUT_DIR/video.mp4"
OUTPUT_PREVIEW="$OUTPUT_DIR/video-preview.mp4"

# Frames per second the render-app compositions are defined at
# (render-app/src/ChunkView.tsx). Only used to turn --preview seconds
# into a frame range.
VIDEO_FPS=30
# Empty means "render the whole video"; set by --preview.
PREVIEW_SECONDS=""

# Wait (briefly) for a TCP port to come free, and say who is holding it
# if it does not. An interrupted run (Ctrl-C, a crashed terminal) can
# leave a server behind; without this the next run just reports
# "failed to start" and the reason is buried in a log file.
wait_for_port_free() {
  local port="$1"
  local attempts=20   # ~5s

  if ! command -v lsof >/dev/null 2>&1; then
    sleep 1
    return 0
  fi

  while [ "$attempts" -gt 0 ]; do
    if [ -z "$(lsof -ti tcp:"$port" 2>/dev/null)" ]; then
      return 0
    fi
    sleep 0.25
    attempts=$((attempts - 1))
  done
  return 1
}

for arg in "$@"; do
  case "$arg" in
    --no-render)
      RENDER_FLAG="--no-render"
      RENDER_ENABLED=0
      RUN_SEGMENT_INDEX=0
      RUN_VIDEO_RENDER=0
      ;;
    --backend-only)
      RUN_WEB_SERVER=0
      RUN_NPM_INSTALL=0
      RUN_DOCS_SERVER=0
      RUN_SEGMENT_INDEX=0
      RUN_VIDEO_RENDER=0
      ;;
    --web-only)
      # Browse whatever a previous run left on disk. Starts nothing
      # else and spends no time on narration or rendering.
      RUN_BACKEND=0
      RUN_NPM_INSTALL=0
      RUN_DOCS_SERVER=0
      RUN_SEGMENT_INDEX=0
      RUN_VIDEO_RENDER=0
      ;;
    --skip-web) RUN_WEB_SERVER=0 ;;
    --skip-docs-server) RUN_DOCS_SERVER=0 ;;
    --preview) PREVIEW_SECONDS=120 ;;
    --preview=*)
      PREVIEW_SECONDS="${arg#*=}"
      case "$PREVIEW_SECONDS" in
        ''|*[!0-9]*)
          echo "--preview takes a whole number of seconds, e.g. --preview=120" >&2
          exit 2
          ;;
      esac
      if [ "$PREVIEW_SECONDS" -lt 1 ]; then
        echo "--preview needs at least 1 second." >&2
        exit 2
      fi
      ;;
    --stop-web)
      if [ -f "$WEB_PID_FILE" ] && kill -0 "$(cat "$WEB_PID_FILE")" 2>/dev/null; then
        kill "$(cat "$WEB_PID_FILE")" 2>/dev/null || true
        rm -f "$WEB_PID_FILE"
        echo "Stopped the React viewer."
      else
        rm -f "$WEB_PID_FILE"
        echo "No React viewer is running (per $WEB_PID_FILE)."
      fi
      # An interrupted run can orphan a server the pid file no longer
      # knows about, which would block the next start.
      if ! wait_for_port_free "$WEB_PORT"; then
        echo "Something is still listening on port $WEB_PORT. Free it with:" >&2
        echo "    lsof -ti tcp:$WEB_PORT | xargs kill" >&2
      fi
      exit 0
      ;;
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
      sed -n '2,42p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 1
      ;;
  esac
done

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

# Install a package's node modules when they are missing OR out of date.
#
# Checking only for the node_modules directory is not enough: after a
# `git pull` that adds a dependency, node_modules still exists, the
# install is skipped, and the missing package surfaces much later as a
# baffling build error (e.g. "Rollup failed to resolve import
# \"mermaid\"" from the docs viewer). npm rewrites
# node_modules/.package-lock.json on every install, so comparing it
# against package.json / package-lock.json tells us whether what is on
# disk still matches what is declared.
ensure_node_modules() {
  local dir="$1"
  local label="$2"
  local stamp="node_modules/.package-lock.json"

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm (Node.js) is required but was not found on PATH." >&2
    return 1
  fi

  cd "$dir" || return 1

  if [ ! -d node_modules ]; then
    echo "Installing $label's node modules (first run)..."
    npm install
  elif [ ! -f "$stamp" ] \
    || [ package.json -nt "$stamp" ] \
    || { [ -f package-lock.json ] && [ package-lock.json -nt "$stamp" ]; }; then
    echo "$label's dependencies changed since the last install — running npm install..."
    npm install
  else
    echo "$label's node modules are up to date — skipping."
  fi

  cd "$PROJECT_ROOT" || return 1
}

# Print the live frontend and docs-viewer URLs for this script's docs server.
# Ports/paths on main: DOCS_PORT (default 4173), docs viewer at /docs-viewer/.
print_local_urls() {
  echo ""
  echo "Local URLs:"
  if [ "$RUN_WEB_SERVER" = "1" ]; then
    echo "  Repo viewer:  $APP_URL   <- click a file to watch its explanation"
  fi
  if [ "$RUN_DOCS_SERVER" = "1" ]; then
    echo "  Static root:  $FRONTEND_URL"
    echo "  Docs viewer:  $DOCS_VIEWER_URL"
  fi
}

# Publish a line of progress for the React viewer to show. Best effort:
# a missing venv or a failed write must never stop a run (see
# src/pilot/status.py).
status_update() {
  if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    (cd "$PROJECT_ROOT" && "$PROJECT_ROOT/.venv/bin/python" -m src.pilot.status "$@") \
      >/dev/null 2>&1 || true
  fi
}

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
# 1) React viewer — started FIRST, and independent of everything else
#
# The pipeline takes many minutes (narration audio per chunk, then a
# video per stack). The viewer must not wait for it: it comes up in
# seconds, reads whatever is already on disk, and polls
# render-app/public/status.json so it can show the run's progress and
# unlock each file as its chunk is staged.
# ---------------------------------------------------------------------
run_web_server() {
  log "[1/5] Viewer: starting the React repo viewer"

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm (Node.js) is required for the viewer but was not found on PATH." >&2
    echo "Re-run with --skip-web to carry on without it." >&2
    return 0
  fi

  if ! ensure_node_modules "$PROJECT_ROOT/frontend" "the viewer"; then
    cd "$PROJECT_ROOT"
    echo "Could not install the viewer's dependencies — skipping it." >&2
    echo "Everything else still runs; re-run with --skip-web to silence this." >&2
    return 0
  fi

  mkdir -p "$LOCAL_RUN_DIR"

  # Stop a viewer left over from a previous run before starting a new
  # one, so the port is free (vite is started with --strictPort: a
  # silently different port would make the URL printed here a lie).
  if [ -f "$WEB_PID_FILE" ] && kill -0 "$(cat "$WEB_PID_FILE")" 2>/dev/null; then
    kill "$(cat "$WEB_PID_FILE")" 2>/dev/null || true
  fi
  rm -f "$WEB_PID_FILE"

  if ! wait_for_port_free "$WEB_PORT"; then
    echo "Port $WEB_PORT is still in use — most likely a viewer left behind by" >&2
    echo "a run that was interrupted before it could stop one. Free it with:" >&2
    echo "    lsof -ti tcp:$WEB_PORT | xargs kill" >&2
    echo "or use a different port:  WEB_PORT=5175 ./run-local.sh" >&2
    echo "Carrying on without the viewer; everything else is unaffected." >&2
    return 0
  fi

  # Run vite's own binary rather than `npx vite`: npx stays alive as a
  # parent process, so $! would be npx's pid and killing it can leave
  # the real server holding the port. exec'ing the binary makes the pid
  # we record the pid that --stop-web has to kill.
  ( cd "$PROJECT_ROOT/frontend" && exec node_modules/.bin/vite --port "$WEB_PORT" --strictPort ) \
    > "$WEB_LOG_FILE" 2>&1 &
  echo $! > "$WEB_PID_FILE"
  sleep 1.5

  if kill -0 "$(cat "$WEB_PID_FILE")" 2>/dev/null; then
    echo "Repo viewer running (background):  $APP_URL"
    echo "(stop it with: ./run-local.sh --stop-web)"
  else
    echo "The repo viewer failed to start:" >&2
    sed -n '1,6p' "$WEB_LOG_FILE" >&2
    echo "(full log: $WEB_LOG_FILE)" >&2
    echo "Everything else still runs; re-run with --skip-web to silence this." >&2
  fi
}

# ---------------------------------------------------------------------
# 2) Python backend pipeline, default configuration
# ---------------------------------------------------------------------
run_backend() {
  log "[2/5] Backend: setting up Python environment"

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

  if [ "$RENDER_ENABLED" = "1" ]; then
    # One-time ~64MB download of the Piper Indian-English narration
    # voice (see src/render/tts.py). Non-fatal if it can't be reached
    # (e.g. this project's own dev sandbox blocks huggingface.co) —
    # synthesis just falls back to espeak-ng either way.
    python scripts/ensure_piper_voice.py
  fi

  log "[2/5] Backend: running the pipeline (detect -> chunk -> extract -> narrate -> render)"
  python scripts/run_backend_pilot.py $RENDER_FLAG

  deactivate
}

# ---------------------------------------------------------------------
# 3a) Install render-app's node modules
# ---------------------------------------------------------------------
run_npm_install() {
  log "[3/5] Render app: installing render-app's node modules"

  ensure_node_modules "$PROJECT_ROOT/render-app" "render-app"
}

# ---------------------------------------------------------------------
# 3b) Start a local server so the documentation is viewable in a browser
# ---------------------------------------------------------------------
run_docs_server() {
  log "[3/5] Docs: building and serving the documentation viewer"

  # A docs-viewer build failure must not take the run down with it:
  # the expensive work (narration, the stack videos) and the repo
  # viewer are unrelated to it, and `set -e` would otherwise abort the
  # whole script over documentation that is not the point of the run.
  # The static server still goes up — render-app/public is also what
  # serves the staged chunks — it just carries a stale /docs-viewer/.
  cd "$PROJECT_ROOT/render-app"
  if npm run build:docs; then
    DOCS_BUILD_OK=1
  else
    DOCS_BUILD_OK=0
    echo "" >&2
    echo "The documentation viewer failed to build — carrying on without" >&2
    echo "rebuilding it. $DOCS_VIEWER_URL will show the previous build," >&2
    echo "or 404 if there has never been one. Everything else in this run" >&2
    echo "is unaffected." >&2
    echo "If the error above is an unresolved import, a dependency in" >&2
    echo "render-app/package.json is not installed — run:" >&2
    echo "    cd render-app && npm install" >&2
    echo "" >&2
  fi
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
    if [ "${DOCS_BUILD_OK:-1}" = "1" ]; then
      echo "Documentation server running (background)."
    else
      echo "Documentation server running (background) — with a stale docs viewer."
    fi
    print_local_urls
    echo "(stop it with: ./run-local.sh --stop-docs-server)"
  else
    echo "Documentation server failed to start — see $DOCS_LOG_FILE" >&2
  fi
}

# ---------------------------------------------------------------------
# 4) Index where each file appears inside its stack video
#
# Runs BEFORE the render: the offsets are computed from the staged
# bundles, not from the mp4, so the viewer can already show every
# file's chapter table while the videos are still encoding.
# ---------------------------------------------------------------------
run_segment_index() {
  if [ ! -f render-app/public/chunks/manifest.json ]; then
    return 0
  fi

  log "[4/5] Index: locating each file inside its stack video"
  status_update --phase indexing

  cd "$PROJECT_ROOT/render-app"
  if npx --yes tsx scripts/build-segment-index.ts; then
    cd "$PROJECT_ROOT"
  else
    cd "$PROJECT_ROOT"
    echo "Could not build the segment index — the viewer will still list" >&2
    echo "the files, but clicking one cannot jump to its moment in the video." >&2
    echo "Re-run just this step with:" >&2
    echo "    cd render-app && npx --yes tsx scripts/build-segment-index.ts" >&2
  fi
}

# ---------------------------------------------------------------------
# 5) Render the pipeline's output to a real video file at a fixed path
# ---------------------------------------------------------------------
sync_manifest_phase_style() {
  if [ ! -f pipeline.config.yaml ]; then
    echo "No pipeline.config.yaml — cannot sync video.phaseStyle into manifests." >&2
    return 1
  fi
  log "[5/5] Video: syncing video.phaseStyle from pipeline.config.yaml into chunk manifests"
  if ! python3 scripts/sync_manifest_phase_style.py; then
    echo "Could not sync phaseStyle into Remotion manifests." >&2
    return 1
  fi
}

run_video_render() {
  if [ ! -f render-app/public/chunks/manifest.json ]; then
    echo "No rendered chunks are staged at render-app/public/chunks/ —" >&2
    echo "run the backend step first without --no-render so there is" >&2
    echo "something to render." >&2
    exit 1
  fi

  sync_manifest_phase_style || exit 1

  mkdir -p "$OUTPUT_DIR"

  cd "$PROJECT_ROOT/render-app"

  # ---- browser detection (shared across all renders) ----

  # In some sandboxed Linux CI/dev environments, Remotion's own
  # headless-Chromium download is blocked by the network allowlist
  # (see documentation/09-phase6-rendering.md) — fall back to a
  # Playwright Chromium already installed there instead. This glob
  # only ever matches that one specific sandbox path.
  BROWSER_EXECUTABLE=""
  for candidate in /opt/pw-browsers/chromium-*/chrome-linux64/chrome; do
    if [ -x "$candidate" ]; then
      BROWSER_EXECUTABLE="$candidate"
      break
    fi
  done

  # On macOS, Remotion's own downloaded Chrome Headless Shell is a
  # common source of the "Target closed" crash (see
  # https://remotion.dev/docs/target-closed) — Intel Macs in
  # particular aren't covered by Remotion's browser-fix build, and a
  # Gatekeeper-quarantined or partially-downloaded binary fails the
  # same way. Remotion's own documented workaround is
  # --browser-executable pointing at a real, already-installed
  # browser, so prefer one if we can find it.
  if [ -z "$BROWSER_EXECUTABLE" ] && [ "$(uname -s)" = "Darwin" ]; then
    for candidate in \
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      "/Applications/Chromium.app/Contents/MacOS/Chromium" \
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
      "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    do
      if [ -x "$candidate" ]; then
        BROWSER_EXECUTABLE="$candidate"
        echo "Using locally installed browser for rendering: $candidate"
        break
      fi
    done
    if [ -z "$BROWSER_EXECUTABLE" ]; then
      echo "No local Chrome/Chromium/Edge/Brave found — falling back to" >&2
      echo "Remotion's own downloaded browser. If the render crashes with" >&2
      echo "\"Target closed\", install Google Chrome and re-run, or set" >&2
      echo "REMOTION_BROWSER_EXECUTABLE to a Chrome/Chromium binary path." >&2
    fi
  fi

  # Always allow an explicit override, regardless of platform.
  if [ -n "${REMOTION_BROWSER_EXECUTABLE:-}" ]; then
    BROWSER_EXECUTABLE="$REMOTION_BROWSER_EXECUTABLE"
  fi

  # Default to a single concurrent browser tab. Remotion's headless
  # Chromium can crash mid-render ("Target closed" — see
  # https://remotion.dev/docs/target-closed) when several tabs compete
  # for memory/CPU; rendering one frame batch at a time is slower but
  # far more reliable on a laptop. Override with REMOTION_CONCURRENCY.
  RENDER_CONCURRENCY="${REMOTION_CONCURRENCY:-1}"

  # ---- helper: render one composition to one video file ----
  render_one_composition() {
    local COMP_ID="$1"
    local TARGET="$2"
    local LABEL="$3"

    local RENDER_ARGS=("$COMP_ID" "$TARGET" "--concurrency=$RENDER_CONCURRENCY")
    if [ -n "$BROWSER_EXECUTABLE" ]; then
      RENDER_ARGS+=(--browser-executable="$BROWSER_EXECUTABLE")
    fi
    if [ -n "$PREVIEW_SECONDS" ]; then
      local LAST_PREVIEW_FRAME=$(( PREVIEW_SECONDS * VIDEO_FPS - 1 ))
      if [ "$LAST_PREVIEW_FRAME" -lt 0 ]; then
        LAST_PREVIEW_FRAME=0
      fi
      RENDER_ARGS+=("--frames=0-$LAST_PREVIEW_FRAME")
    fi
    if [ "${RUN_LOCAL_VERBOSE:-0}" = "1" ]; then
      RENDER_ARGS+=(--log=verbose)
    fi

    echo "  Rendering $LABEL -> $TARGET"
    if ! npx remotion render "${RENDER_ARGS[@]}"; then
      echo "" >&2
      echo "Video render failed for $LABEL ($COMP_ID)." >&2
      echo "This is almost always Remotion's headless Chromium crashing" >&2
      echo "on launch or mid-render (see https://remotion.dev/docs/target-closed)." >&2
      echo "Currently using browser executable:" >&2
      echo "  ${BROWSER_EXECUTABLE:-<the Chrome Headless Shell that Remotion itself downloaded>}" >&2
      echo "See run-local.sh --help for troubleshooting." >&2
      return 1
    fi
  }

  # ---- discover which stacks have per-stack manifests ----
  # The combined manifest's "stacks" field lists them, but we can also
  # just look for <stack>/manifest.json directories on disk.
  DETECTED_STACKS=()
  for stack_manifest in "$PROJECT_ROOT"/render-app/public/chunks/*/manifest.json; do
    if [ -f "$stack_manifest" ]; then
      stack_name="$(basename "$(dirname "$stack_manifest")")"
      DETECTED_STACKS+=("$stack_name")
    fi
  done

  if [ "${#DETECTED_STACKS[@]}" -gt 0 ]; then
    # ---- per-stack rendering ----
    if [ -n "$PREVIEW_SECONDS" ]; then
      log "[5/5] Video: rendering ${PREVIEW_SECONDS}s PREVIEW per stack (${DETECTED_STACKS[*]})"
    else
      log "[5/5] Video: rendering per-stack videos (${DETECTED_STACKS[*]})"
    fi
    status_update --phase rendering

    RENDERED_VIDEOS=()
    RENDER_FAILED=0
    for stack in "${DETECTED_STACKS[@]}"; do
      if [ -n "$PREVIEW_SECONDS" ]; then
        TARGET="$OUTPUT_DIR/video-${stack}-preview.mp4"
      else
        TARGET="$OUTPUT_DIR/video-${stack}.mp4"
      fi
      if render_one_composition "StackVideo-${stack}" "$TARGET" "$stack"; then
        RENDERED_VIDEOS+=("$TARGET")
        # Tell the viewer this one is watchable now, rather than making
        # the user wait for every other stack to finish rendering.
        status_update --video-ready "$stack" --video-file "$(basename "$TARGET")"
      else
        RENDER_FAILED=1
      fi
    done

    if [ "$RENDER_FAILED" = "1" ] && [ "${#RENDERED_VIDEOS[@]}" -eq 0 ]; then
      cd "$PROJECT_ROOT"
      echo "All per-stack renders failed." >&2
      status_update --error "Every per-stack video render failed."
      exit 1
    fi
  else
    # ---- fallback: single combined video (no per-stack manifests) ----
    if [ -n "$PREVIEW_SECONDS" ]; then
      RENDER_TARGET="$OUTPUT_PREVIEW"
      log "[5/5] Video: rendering a ${PREVIEW_SECONDS}s PREVIEW to output/video-preview.mp4"
    else
      RENDER_TARGET="$OUTPUT_VIDEO"
      log "[5/5] Video: rendering output/video.mp4"
    fi
    status_update --phase rendering

    if ! render_one_composition "FullVideo" "$RENDER_TARGET" "combined"; then
      cd "$PROJECT_ROOT"
      status_update --error "The combined video render failed."
      exit 1
    fi
    RENDERED_VIDEOS=("$RENDER_TARGET")
  fi

  cd "$PROJECT_ROOT"

  if [ -n "$PREVIEW_SECONDS" ]; then
    echo "Preview(s) written (first ${PREVIEW_SECONDS}s only):"
    for v in "${RENDERED_VIDEOS[@]}"; do echo "  $v"; done
    echo "Re-run without --preview to produce the complete video(s)."
  else
    echo "Video(s) written:"
    for v in "${RENDERED_VIDEOS[@]}"; do echo "  $v"; done
  fi
}

# The viewer goes up first and stays up: everything after this point
# can take tens of minutes, and the whole point is to be able to watch
# it happen.
if [ "$RUN_WEB_SERVER" = "1" ]; then run_web_server; fi
if [ "$RUN_BACKEND" = "1" ]; then run_backend; fi
if [ "$RUN_NPM_INSTALL" = "1" ]; then run_npm_install; fi
if [ "$RUN_DOCS_SERVER" = "1" ]; then run_docs_server; fi
if [ "$RUN_SEGMENT_INDEX" = "1" ]; then run_segment_index; fi
if [ "$RUN_VIDEO_RENDER" = "1" ]; then run_video_render; fi
if [ "$RUN_VIDEO_RENDER" = "1" ]; then status_update --done; fi

log "Done."
if [ "$RUN_WEB_SERVER" = "1" ] || [ "$RUN_DOCS_SERVER" = "1" ]; then print_local_urls; fi
if [ "$RUN_VIDEO_RENDER" = "1" ]; then
  echo "Videos:        $OUTPUT_DIR/video-<stack>.mp4 (one per detected stack)"
fi

exit 0
