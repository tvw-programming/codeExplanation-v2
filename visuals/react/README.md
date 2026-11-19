# React visuals (Slice A)

Stack subfolder under the shared `visuals/` package (Q6 B).

Per-chunk artifacts are written here during render:

```
visuals/react/<chunkId>/
  visualGraph.json
  lifecycleFlows.json
  interactive.json
```

Cursor canvas: copy `canvas/ReactBreakdownCanvas.template.tsx` into a
Cursor canvas session and paste the embedded `interactive.json` payload
(no network fetch). Remotion end card + measured-beat audio ships in
`VisualBreakdownStill` when `interactiveBreakdown` is available/partial.
