# express visuals

Stack subfolder under shared `visuals/` (Q6 B). Artifacts: `visuals/express/<chunkId>/`.

Extractor honesty (`src/extract/express/`, `EXTRACTOR_VERSION` 14):

- Nested in-file literal `use(prefix, router)` mounts compose (like Fiber groups).
- Path-string arrays emit one route per literal; non-literals skipped.
- RegExp route paths are recorded as `<regex:…>` with `assumed=true` (no forged URL).
- `use(prefix, non-router)` is path-scoped middleware, not a mount edge.
- Non-literal mount prefixes / unmounted routers → `assumed` (never invent).
- Per-route `METHOD(path, mw…, handler)` identifiers feed lifecycle middleware.
