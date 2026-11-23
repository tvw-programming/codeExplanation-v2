# express visuals

Stack subfolder under shared `visuals/` (Q6 B). Artifacts: `visuals/express/<chunkId>/`.

Extractor honesty (`src/extract/express/`, `EXTRACTOR_VERSION` 19):

- Nested in-file literal `use(prefix, router)` mounts compose via shared `PrefixGraph`.
- Cross-file `app.use(prefix, require('./…'))` joins only on unique literal module
  resolution (ambiguous / package / missing → assumed/skip; never invent).
- Path-string arrays emit one route per literal; non-literals skipped.
- RegExp route paths are recorded as `<regex:…>` with `assumed=true` (no forged URL).
- `use(prefix, non-router)` is path-scoped middleware, not a mount edge.
- Non-literal mount prefixes / unmounted routers → `assumed` + `pathResolved=false`.
- Per-route `METHOD(path, mw…, handler)` identifiers feed lifecycle middleware.
