# Phase 0 — Scaffolding, Dynamic Repo Input, Security Guardrails

Status: done. 14 tests at phase completion (security/config tests have
since grown — see [`10-phase7-pilot-and-validation.md`](./10-phase7-pilot-and-validation.md)
for the current total).

## What this phase delivers

1. The pipeline repo structure and `pipeline.config.yaml` loader.
2. **Dynamic repo input**: accept any git URL or local path, resolve it
   to a local directory — no hardcoded repo anywhere.
3. **Security guardrails**: never read `.env*`/`*.pem`/`*secrets*`
   files; treat repository content as data, never instructions; scan
   for secret-shaped strings before any snippet reaches a chunk file.

## Locked rules this phase implements

- Source is always read from config or an explicit override — never
  hardcoded (`docs/implementation-plan-phased.md`, Phase 0).
- `never_read_patterns`: `.env*`, `*.pem`, `*secrets*` — enforced before
  any file is read, not just filtered out of final output.
- `secret_scan_before_write: true` — every code snippet must pass
  through a secret scan before it is written to a chunk record.

## Key functions and why they were chosen

### `src/config/load_config.py: load_config(path)`

**What it does:** parses `pipeline.config.yaml`, validates the four
required top-level sections exist, and returns a typed `PipelineConfig`
dataclass (not a raw dict).

**Why a typed dataclass instead of passing the raw YAML dict around:**
a raw dict lets a typo in a key (`"souce"` instead of `"source"`) fail
silently deep inside some later phase, far from where the mistake was
made. Converting to dataclasses at load time means every required field
is checked exactly once, at startup, with a clear `ConfigError` pointing
at the missing key — not a `KeyError` three function calls deep during
an actual pipeline run.

**Why `PipelineConfig.resolve_source(override=None)` exists as a method
on the config object, rather than scattering `if override: ... else: ...`
logic at each call site:** there is exactly one place in the codebase
that decides "which repo are we actually running against," and every
caller (the pilot runner, a future CLI) goes through it. This is what
makes "any repo as input" a property of the architecture rather than a
convention every caller has to remember.

### `src/detect/source_resolver.py: resolve_source(value, workdir)`

**What it does:** given a string that is either an existing local path
or something that looks like a git URL, returns a `ResolvedSource`
(kind, original value, resolved local root) — cloning via `git clone
--depth 1` when needed.

**Why `--depth 1` (shallow clone) instead of a full clone:** the
pipeline only ever reads the current state of the files, never commit
history, within this module. (Commit/PR history is looked up separately
and intentionally via `gh api` in Phase 4's `pull_request_lookup.py`,
not by cloning full git history.) A shallow clone is faster and uses a
fraction of the disk, with no functional downside for this phase's job.

**Why `_looks_like_git_url()` checks for `git@` OR `(http/https scheme
+ .git suffix OR github.com host)` instead of just "does it start with
`http`":** a bare `http://` check would also accept an arbitrary local
file-server URL or something that merely looks URL-shaped, and more
importantly would NOT correctly distinguish "this is a git remote" from
"this is just some other web page the user pasted" — so the function
narrows to the actual two shapes git URLs take in practice (SSH-style
`git@host:path` and a `.git` or recognized git-hosting-service HTTPS
URL), which then also naturally rejects malformed inputs rather than
attempting a clone against them and failing with a confusing git error.

**Why the clone slug/destination is validated against path traversal
(`_slug_from_url` output checked for `""`, `"."`, `".."`, or any `/`/`\\`)
and the resolved destination is double-checked to be a true child of the
workdir — rather than trusting whatever `git clone`'s target directory
argument resolves to:** this is a security fix added after a code
review (see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)
for the exact incident) found that a crafted source value ending in a
directory-traversal segment (e.g. `.../someorg/..`) produced a slug of
`".."`, which resolved the "clone destination" to the workdir's own
**parent** — an arbitrary, already-existing directory — and silently
skipped the clone step entirely (because that parent directory already
"existed"), handing the rest of the pipeline the wrong directory to
scan. Rejecting unsafe slugs up front, and independently re-verifying
the resolved path is inside the workdir before trusting it, closes this
without weakening the "any repo as input" guarantee — a legitimately-named
repo is unaffected.

**Why `_host_is_github()` does an exact-or-subdomain host match instead
of `"github.com" in parsed.netloc`:** the substring check would also
accept a lookalike host such as `github.com.attacker.net` as if it were
really GitHub, because the string `"github.com"` does appear inside it
— just not as the actual host. A real exact-or-subdomain comparison
(`host == "github.com" or host.endswith(".github.com")`) is the correct
way to validate a hostname and costs nothing extra.

**Why a `"--"` argument separator is placed before the repo URL in the
`git clone` argv** (`["git", "clone", "--depth", "1", "--", value, str(dest)]`):
defense in depth. `_looks_like_git_url()` already prevents most
flag-injection-shaped values from reaching this call, but `--` is the
standard, zero-cost way to tell `git` "everything after this is a
positional argument, never a flag," so a future change to the URL
validation can't accidentally reopen an argument-injection path.

### `src/security/guardrails.py`

**What it does:** `is_blocked_path()` / `filter_blocked_paths()` (glob-based
file blocking), `secret_scan()` (raises `SecretFoundError` on a
secret-shaped match), `redact_secrets()` (non-raising counterpart,
returns `(text, bool)`), and `assert_safe_to_read()`.

**Why two functions for secret handling (`secret_scan` that raises, and
`redact_secrets` that doesn't) instead of one:** different call sites
need different failure modes. Reading a file that matches a blocked
glob pattern (`.env`, `*.pem`) should hard-stop — there is no safe
partial read of a secrets file, so `assert_safe_to_read()`/`secret_scan()`
raising is correct there. But a single code *snippet* extracted from an
otherwise-legitimate source file matching one of the deliberately broad,
false-positive-prone secret patterns should not crash the entire
chunk's extraction — redacting that one snippet and flagging the chunk
for human review (lower confidence, a note) is a far better failure
mode than losing the whole chunk's legitimate content over one matched
substring. `redact_secrets()` exists specifically for that second case
(wired into `extract/common.py: trim_snippet()` — see Phase 3's doc and
the security incident writeup in the gaps doc for why this wiring was
missing for seven phases and how it was found and fixed).

**Why the regex patterns in `_SECRET_PATTERNS` are deliberately broad
("coarse secret-shaped patterns... it is expected to produce false
positives, and false positives are the safe failure mode here") instead
of trying to be a precise, low-false-positive secret detector:** a
missed real secret is a far worse outcome than an over-eager redaction
of something that merely looked like one. The module's own docstring
states this trade-off explicitly rather than leaving it implicit.

**Why path-blocking is glob-pattern based (`fnmatch`) rather than an
explicit list of filenames:** an explicit list (`.env`, `.env.local`,
`.env.production`, ...) would need updating every time a new environment
file naming convention appeared. `.env*` as a glob covers the whole
family with one entry, and is still just as easy for a human to audit
in `DEFAULT_BLOCKED_PATTERNS` as an explicit list would be.

## Verified against the real repo

Phase 0's config loader and guardrails were exercised indirectly through
every later phase's real-repo runs (see Phase 7's pilot report). The
security fixes (path traversal, hostname substring match, secret
redaction wiring) were specifically re-verified with a post-fix pilot
run against `alumni-web` showing identical output to the pre-fix run —
confirming the real repo genuinely contains no secrets and the fixes
introduce no regression (see [`13-known-gaps-and-roadmap.md`](./13-known-gaps-and-roadmap.md)).
