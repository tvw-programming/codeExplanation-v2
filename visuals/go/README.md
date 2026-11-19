# Go Fiber visuals

Stack subfolder under the shared `visuals/` package (Q6 B). Chunk stack id is `go`.

Per-chunk artifacts are written here during render:

```
visuals/go/<chunkId>/
  visualGraph.json      # kind: route_tree
  lifecycleFlows.json   # middleware → handler → response
  interactive.json
```

Developer-centric unit: one file/package chunk’s routes, handlers, and
ordered middleware — not end-to-end business journeys.

Cursor canvas: copy `canvas/GoFiberBreakdownCanvas.template.tsx` into a
Cursor canvas session and paste the embedded `interactive.json` payload
(no network fetch). Remotion end card + measured-beat audio ships in
`VisualBreakdownStill` when `interactiveBreakdown` is available/partial.

Brand: Go cyan `#00ADD8` + Fiber green `#00C853` (middleware edges);
logo `visuals/logos/go-fiber.svg` top-right.
