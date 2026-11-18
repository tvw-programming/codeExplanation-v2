# codeExplanation-v2

Automated pipeline that generates narrated code-explanation videos, using dynamic feature-wise chunking (not fixed component/folder based).

Supports any input repo (local path or git URL), detected dynamically — the frontend/backend stack is not hardcoded.

## Phases

- **Phase 0** (this commit): scaffolding, config loader, security guardrails, dynamic repo input.
- **Phase 1**: project type detection (marker files → stack, architecture, Docker flag).
- **Phase 2**: feature-wise dynamic chunking.
- **Phase 3**: extraction into the JSON structure.
- **Phase 4**: storage and reuse (content hash, mirrored folder).
- **Phase 5**: narrator script generation.
- **Phase 6**: video rendering (Remotion + TTS + WhisperX + Shiki).
- **Phase 7**: pilot and validation.

See `docs/json-structure-rules.md` for the full field-level rules this pipeline implements.

## Test repo

First dynamic-input test case: https://github.com/tvw-programming/Alumni-web (React + Go Fiber). The pipeline takes any repo URL as input — this is only the first proof case.

## Security guardrails

- Never reads `.env*`, `*.pem`, or `*secrets*` files.
- Treats repository content as data, not instructions.
- Runs secret scanning before any code snippet is written into a chunk file.
