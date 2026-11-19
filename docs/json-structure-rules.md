# JSON Structure Rules

Each field is keyed by name. Each entry has: required (yes/no) and rules.

## chunkId
- required: yes
- Readable feature-name prefix plus a short hash of file path and feature name together, e.g. auth-login-3f9a2c.
- Stable across runs unless the file moves.

## filePath
- required: yes
- Path relative to project root, forward slashes.
- If a chunk spans several files, holds the primary (defining) file. Others go in dependencies.

## featureName
- required: yes
- Short human-readable name, e.g. "Auth Login". Taken from folder or main file name.

## projectType
- required: yes
- Holds three parts: frontend stack, backend stack, architecture (monolith or microservice).
- Includes a Dockerized flag (yes/no).
- A pure Python AI agent has an empty frontend part.
- No "unknown" fallback value.

## language
- required: yes
- Dynamic: the programming language detected from the file (e.g. Go, Java, Python, TypeScript, JavaScript, C#, PHP, HTML).
- Top ten popular languages are handled first, but the field is not a fixed list.

## lineRange
- required: yes
- Start and end line of the chunk in the primary file. Start is never after end.

## frameworkOrLibrary
- required: yes
- Array; primary library first, rest in any order. May be empty if the file uses no external libraries.
- Lists only libraries actually imported in the chunk, not installed-only ones.
- Libraries come from each language's own ecosystem (e.g. React, Angular, Gin, GORM, Spring Boot, .NET).

## inputs
- required: no
- What the chunk receives: props (React), inputs (Angular), request parameters (Go Fiber, Spring Boot), function arguments (Python).
- Each entry: name, type, default, description.

## outputs
- required: no
- What the chunk produces: callbacks and emitted events (React, Angular), return values (Python), response bodies with status codes (Go Fiber, Spring Boot).
- Each entry: name, type, description.

## eventHandlers
- required: no
- Must capture every event handler in the chunk, none skipped. If not fully analyzed, still listed and marked assumed with a note.
- Each entry: name, signature, one-line description, eventType (user action or system generated).
- For components with 20+ handlers, every handler is still listed; the chunker splits the component into several chunks grouped by purpose.

## apiCalls
- required: no
- Every call to an outside service.
- Postman-style details: method, URL or URL pattern, headers, query parameters, sample request body, sample response with status code, and what the response is used for.
- If the URL is a variable, the pattern holds the variable and is marked assumed.

## importantFunctions
- required: no
- Key functions beyond event handlers. Each entry: name, signature, description, line range.
- Source code snippet is mandatory, trimmed to 120 lines. Longer functions continue in follow-on snapshots, not cut off.
- Video step renders the snippet with highlighting.

## sideEffects
- required: no
- Anything the chunk does beyond returning a value: database writes, external calls, global state changes, timers, subscriptions, logging.
- Each entry: type, description.

## featureMapping
- required: yes
- Connections between chunks: other chunks it mounts, calls, or depends on, by chunkId.
- Frontend API calls are matched to backend routes by URL.
- May be an empty list when the chunk stands alone.

## dependencies
- required: no
- Internal files this chunk imports, by relative path, with what each is used for.
- External libraries stay in frameworkOrLibrary.

## dataModels
- required: no
- Types, interfaces, schemas, or entities used: TypeScript interfaces, Pydantic models, Go structs, Java entities.
- Each entry: name, fields with types, file where defined.
- Code snippet of the definition is mandatory, trimmed to 120 lines; longer continues in follow-on snapshots.

## routes
- required: no
- Pages or endpoints the chunk defines or serves.
- Each entry: path, type (static or dynamic), routing library (e.g. React Router, Angular router, Fiber router, Spring Boot web mapping), allowed HTTP methods, middleware or guards, typed parameters, protected (yes/no), handler it maps to.

## confidence
- required: yes
- Number from 0 to 1, set by how sure the extractor is.

## confidenceLevel
- required: yes
- Label derived from confidence: high, medium, or low.

## notes
- required: no
- Anything the reviewer should verify.

---

## Storage and reuse

### Folder layout
- Chunk JSON files are saved in a dummy folder inside the code explanation project.
- The folder mirrors the client repo's structure.
- Each chunk's JSON lives at the path of its primary file, even when the chunk pulls from several files.

### Per-chunk record fields (required)
- contentHash: a content hash of the primary source file. Required.
- lastUpdated: timestamp of the last analysis of this chunk. Required.
- pullRequest: full URL of the pull request that last changed this component. Required.

### Reuse rule
- On later runs, compare the current content hash against the stored one.
- If they match, reuse the stored JSON without re-analysis.
- If they differ, re-analyze only that chunk.
- Example: a data table update re-analyzes only the data table chunks.

---

## Narrator script rules (step seven)

### Section structure
- Each chunk's script has four beats: purpose, how the parts connect, step-by-step flow, and recap with a scope limit.
- Give the reason before the mechanism.
- Name flows by when they run, not by file path.
- Do not read code line by line. Narrate what the code does not show on screen.
- If the flow beat runs past about 60 seconds, split it into two beats.

### Length
- Target 90 to 180 seconds of narration per chunk.
- At about 130 words per minute, 90 seconds is roughly 170 to 180 words, and 180 seconds is roughly 340 to 355 words. Add 10 to 15 percent for pauses.

### Sentence and wording style (TTS-friendly)
- Keep sentences to about 20 words. This is a working limit, not a sourced rule.
- Use present tense and active voice.
- Define a new term right after introducing it.
- Use one idea per sentence.

### Identifiers and pronunciation
- Use a lookup table that maps each identifier (camelCase, snake_case, routes) to its spoken form.
- Test the table per voice before rendering.
- Use SSML tags for characters or phonemes where the voice needs them.

### Linking narration to code highlights
- Use WhisperX word timings as the time base.
- Store the word index for each VISUAL[HIGHLIGHT:id] token, and map each id to a line range.
- Convert seconds to frames with frame = seconds x fps. Drive highlights with useCurrentFrame() and interpolate() in Remotion.
- Apply highlight lines with Shiki decorations or notation transformers.
- If WhisperX cannot time an identifier, anchor the cue to the nearest timed word and widen the window by about 200 ms.
- If a cue still cannot be aligned, mark it assumed: true.
- Verify the timing of camelCase names and file paths with a local test. This behavior is not documented.

### Accuracy and uncertainty
- Restrict every named symbol and call edge to the extraction's symbol table. Validate each one mechanically.
- Speak only verified claims.
- Speak assumed-but-grounded claims using a fixed hedge phrase from the script.
- Leave unverified claims out of the speech.
- Never read the notes field aloud. Keep it for reviewers.
- The 0.85 confidence threshold is a starting point, not a validated value.

### Continuity across chunks
- Keep a glossary or registry keyed by stable IDs, with one canonical name per symbol and a short summary per chunk.
- Use back-references only where feature mapping shows a real earlier link.
- Use forward previews only where the extraction shows a real later call.
- Process dependencies first, so later chunks can point back to earlier ones.

### Long functions split across snapshots
- Keep a coverage ledger of line ranges for each function, and check it for gaps and overlaps.
- Split only at statement boundaries from the parser, never mid-statement.
- Pass a rolling summary and the previous chunk's last lines into the next chunk's prompt.
- Use script-generated continuation markers, and re-run only the gap ranges.

### Source notes
- Most accuracy evidence comes from code QA and documentation tasks, not narration.
- The Shiki and WhisperX mapping is a proposed design. No published example combines them.
- The 200 and 800 line chunk thresholds and the 0.85 threshold come from the project's chunk prompt, not from research.

---

## Implementation notes (code vs these rules — annotate, do not rewrite)

These rules remain the locked source of truth. The live pipeline
diverges in the following ways; see `documentation/` for the narrative.

- **`outputs`**: required-in-rules as an optional field; **always `[]`
  in code** (`json_builder.py`). Known gap.
- **SSML pronunciation tags**: specified under Identifiers; the
  pronunciation table is **built and never applied**. Identifiers are
  spoken as written (see `documentation/15-narration-style-guide.md`).
- **WhisperX word timings / Shiki decorations**: specified under
  Linking narration to code highlights. Live path is **measured-beat
  alignment** (`alignmentSource: "measured-beats"`) and a **CSS
  selection bar** in `ChunkView.tsx`. `shiki` is a dependency, unused.
  `transcribe.mjs` / `estimated_alignment.py` are leftover.
- **Long-function snapshot splitting + coverage ledger**: specified
  under Long functions split across snapshots. **Not implemented.**
  Oversized files are only flagged `needs_further_split`.
- **Reuse rule**: hash match is no longer sufficient.
  `extractorVersion` (currently 4) forces re-analysis when extractors
  change even if source bytes did not.
- Extra record fields not listed above: `fileDescription`,
  `extractorVersion`, `secretsRedacted`, function-context keys,
  `eventHandlers[].lineRange`. Extra bundle fields: `ttsEngine`,
  `fileOverview`, `cardNarration`, `narrationSegments`.
