# Architecture — `src/main.tsx`

**Stack:** `react` · **Chunk:** `src-acd3f3ae` · **Fidelity:** `regex`

> Simplified Mermaid export of the same `visualGraph` / `lifecycleFlows` shown in Remotion. Layout is not pixel-identical to video.

## Availability

- componentTree: `partial`
- lifecycleFlow: `unavailable`
- interactiveBreakdown: `partial`

### Skip / honesty reasons

- `componentTree`: No XProps interface found; prop layer incomplete.
- `lifecycleFlow`: no_lifecycle_triggers_extracted

## Structure

Mount / route / DI / module edges for this chunk (developer-scoped).

```mermaid
flowchart TD
  component_App["App"]
  component_CssBaseline["CssBaseline"]
  component_QueryClientProvider["QueryClientProvider"]
  component_StrictMode["StrictMode"]
  component_ThemeProvider["ThemeProvider"]
  component_main["main"]
  provider_QueryClientProvider["QueryClientProvider"]
  provider_ThemeProvider["ThemeProvider"]
  component_main --> component_App
  component_main --> component_CssBaseline
  component_main --> component_QueryClientProvider
  component_main --> component_StrictMode
  component_main --> component_ThemeProvider
  provider_QueryClientProvider -.-> component_main
  provider_ThemeProvider -.-> component_main
```

## Lifecycle

_No lifecycle diagram (`empty`)._

## Evidence

- `App` — `src/main.tsx:36`
- `CssBaseline` — `src/main.tsx:35`
- `QueryClientProvider` — `src/main.tsx:33`
- `StrictMode` — `src/main.tsx:32`
- `ThemeProvider` — `src/main.tsx:34`
- `main` — `src/main.tsx:1`

## Interactive

Primary exploration is the Cursor canvas over `interactive.json`. Mermaid above is the chat/docs fallback (≤40 nodes).

Docs diagram plan: `flowchart_td`.
