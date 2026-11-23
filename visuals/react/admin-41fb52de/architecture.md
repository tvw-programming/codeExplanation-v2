# Architecture — `src/features/admin/profileRules.ts`

**Stack:** `react` · **Chunk:** `admin-41fb52de` · **Fidelity:** `regex`

> Simplified Mermaid export of the same `visualGraph` / `lifecycleFlows` shown in Remotion. Layout is not pixel-identical to video.

> **Fidelity note:** regex extract — assumed edges may be dashed; empty → no fence.

## Honesty

- Solid arrows (`-->`) = non-assumed edges from the extractor.
- Dashed arrows (`-.->`) or sequence `Note … assumed` = hedged facts.
- Unavailable / empty / too_large → no Mermaid fence (never invent).

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
  component_AlumniDraft["AlumniDraft"]
  component_profileRules["profileRules"]
  component_profileRules --> component_AlumniDraft
  component_profileRules --> component_AlumniDraft
  component_profileRules --> component_AlumniDraft
```

## Lifecycle

_No lifecycle diagram (`empty`)._

## Evidence

- `AlumniDraft` — `src/features/admin/profileRules.ts:86`
- `profileRules` — `src/features/admin/profileRules.ts:1`

## Interactive

Primary exploration is the Cursor canvas over `interactive.json`. Mermaid above is the chat/docs fallback (≤40 nodes).

Docs diagram plan: `flowchart_td`.
