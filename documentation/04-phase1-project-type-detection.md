# Phase 1 — Project Type Detection

Status: done. **Historical** Alumni-web snapshot:
`frontend=react, backend=[go], architecture=monolith, dockerized=true`.

Detection is marker-file based. Frontend flavors from `package.json`
deps: `react`, `angular`, `vue`, `solid`, `qwik`, else `javascript`.
Backend markers include Go, Python, Spring Boot, **Express** (`express`
in deps), and **Rust** (`Cargo.toml`). The old `"react_or_angular"`
catch-all for non-React/Angular packages is gone. See
[`17-multi-stack-visuals.md`](./17-multi-stack-visuals.md).

## What this phase delivers

`src/detect/project_type.py: detect_project_type(root)` returns a
`ProjectType`: frontend stack, backend stack(s), architecture
(`monolith`/`microservice`), a Dockerized flag, plus the raw marker-file
hits and any "unclaimed hint files" for human review.

## Locked rules this phase implements

- Detection is **marker-file based**, never a blind scan for file
  extensions.
- `projectType` has **no `"unknown"` fallback value** — an unmatched
  stack gets an explicit empty/false state instead.
- A pure backend project has an empty frontend part (not a placeholder
  string).

## Key functions and why they were chosen

### `_find_marker_hits(root, max_depth)`

**What it does:** walks the directory tree (bounded depth, skipping
noise directories like `node_modules`/`.git`/`vendor`/`venv`/`dist`) and
records every directory containing one of each stack's marker files.

**Why marker files (`package.json`, `go.mod`, `requirements.txt`,
`pom.xml`/`build.gradle`) instead of scanning for `.py`/`.go`/`.java`
file extensions directly:** a stray `.py` script sitting next to a
React app, with no `requirements.txt`/`pyproject.toml`/`setup.py`
anywhere, is not a Python *project* — it's just a file. Extension-based
detection would misclassify this as "this repo has a Python backend,"
which is wrong and would send that file through the (unimplemented)
Python extractor for no reason. Marker-file detection ties the claim
"this repo has a Go backend" to the actual, recognized convention a Go
project declares itself with (`go.mod`), which is both more accurate
and matches how any experienced engineer would actually answer "what
stack is this repo."

**Why a bounded `max_depth` (default 3) instead of an unbounded
recursive walk:** an unbounded walk inside a large, deeply nested
`node_modules` tree (already explicitly skipped, but depth-bounding is
a second, independent safety net) or a repo with many vendored
dependencies could be extremely slow for no benefit — the marker files
this phase cares about are, by convention, always near the project
root.

### `_find_unclaimed_hints(root, marker_hits, max_depth)`

**What it does:** separately tracks files whose *extension* hints at a
stack (`.py` → Python, `.go` → Go, `.java` → Spring Boot or plain Java)
when that stack has **no marker file anywhere** in the scanned tree.

**Why this exists as a separate, non-authoritative list instead of
either (a) silently ignoring such files or (b) promoting them to a
detected backend stack:** both extremes are wrong. Silently ignoring a
`.py` file that genuinely represents an undetected backend would hide a
real gap from whoever is reviewing the output. Automatically promoting
it to a detected stack risks a false positive — one `.py` script could
be a build helper, not an application. Surfacing it as
`unclaimed_hint_files` is the honest middle ground: a human reviewing
the `ProjectType` output can see "there's a `.py` file here and no
Python marker file — is a marker just missing, or is this not really a
Python backend?" This exact scenario is called out in the module's own
docstring as something that came up directly while testing against the
real alumni repo.

### `_detect_frontend_flavor(package_json_path)`

**What it does:** given a `package.json`, returns a frontend flavor
(`react` / `angular` / `vue` / `solid` / `qwik` / `javascript`) from
declared dependencies, and may also append **`express`** to backend
stacks when `express` is present.

**Why check `dependencies`/`devDependencies` instead of assuming every
`package.json` means React:** `package.json` alone only proves "this is
a JS/TS project." Checking declared deps is how React, Angular, Vue,
Solid, Qwik, plain JavaScript, and Express are told apart without a
silent React default.

### `_detect_java_flavor(root, directory)`

**What it does:** distinguishes `spring_boot` from plain `java` by
checking whether `pom.xml`/`build.gradle(.kts)` actually mentions
`spring-boot`/`org.springframework.boot`. Runtime `MARKER_FILES`
includes `build.gradle.kts`; the example YAML `detection.markers` list
does not (and is unused at runtime — see
[`02-configuration.md`](./02-configuration.md)).

**Why check file contents instead of treating any `pom.xml`/`build.gradle`
as Spring Boot:** same reasoning as the React/Angular case — the
*build-tool* marker (Maven/Gradle) only proves "this is a JVM project."
Whether it's actually a Spring Boot application (which has its own
dedicated extraction/grouping path) or plain Java needs the one extra
check that makes the distinction real rather than assumed.

### Architecture heuristic (`architecture = "microservice" if len(backend_service_roots) > 1 else "monolith"`)

**Why count of distinct backend marker-file directories, instead of,
say, counting Dockerfiles or counting top-level folders:** multiple
independent backend *service roots* (each with its own marker file —
its own `go.mod`, its own `requirements.txt`) is the most direct,
language-agnostic signal of "these are separately deployable services"
available without actually inspecting deployment config. The code
itself documents this as "an inference, not a sourced rule" — a
deliberately honest caveat rather than presenting it as a certainty, in
keeping with the project's confidence-first stance elsewhere.

### `_is_dockerized(root, max_depth)`

**What it does:** true if any `Dockerfile`/`docker-compose.y*ml`/`compose.y*ml`
exists within the bounded walk.

**Why a dedicated, separate flag rather than folding "dockerized" into
the architecture heuristic:** they answer different questions —
"how is this deployed/orchestrated" (Docker) is independent of "is this
one service or several" (architecture). Keeping them separate avoids
one false signal (e.g. a monolith that happens to ship a single
Dockerfile) from corrupting the other's inference.

## Verified against the real repo

> Historical Alumni-web snapshot: `frontend=react, backend=[go],
> architecture=monolith, dockerized=true`.

This was the first point in the pipeline where a real-repo check could
catch a false assumption, and it was run before Phase 2 began. It is
not a live dashboard, and it does not prove Express/Angular/Python
detection quality.
