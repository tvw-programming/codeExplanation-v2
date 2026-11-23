# Architecture — `src/api/alumni.ts`

**Stack:** `react` · **Chunk:** `api-7c64050d` · **Fidelity:** `regex`

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
  component_AlumniPage["AlumniPage"]
  component_AlumniRow["AlumniRow"]
  component_ImportOutcome["ImportOutcome"]
  component_alumni["alumni"]
  component_alumni --> component_AlumniPage
  component_alumni --> component_AlumniPage
  component_alumni --> component_AlumniRow
  component_alumni --> component_AlumniRow
  component_alumni --> component_AlumniRow
  component_alumni --> component_AlumniRow
  component_alumni --> component_ImportOutcome
  component_alumni --> component_ImportOutcome
```

## Lifecycle

_No lifecycle diagram (`empty`)._

## Evidence

- `AlumniPage` — `src/api/alumni.ts:61`
- `AlumniRow` — `src/api/alumni.ts:74`
- `ImportOutcome` — `src/api/alumni.ts:127`
- `alumni` — `src/api/alumni.ts:1`

## Interactive

Primary exploration is the Cursor canvas over `interactive.json`. Mermaid above is the chat/docs fallback (≤40 nodes).

Docs diagram plan: `flowchart_td`.
