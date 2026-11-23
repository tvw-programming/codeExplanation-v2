# Architecture — `src/features/admin/excelWorkbook.ts`

**Stack:** `react` · **Chunk:** `admin-2978afe7` · **Fidelity:** `regex`

> Simplified Mermaid export of the same `visualGraph` / `lifecycleFlows` shown in Remotion. Layout is not pixel-identical to video.

> **Fidelity note:** regex extract — assumed edges may be dashed; empty → no fence.

> **Source of truth:** fences below are exported from this chunk's `visualGraph` / `lifecycleFlows` only — never invented for docs.

## Honesty

- Solid arrows (`-->`) = non-assumed edges from the extractor.
- Dashed arrows (`-.->`) or sequence `Note … assumed` = hedged facts.
- Unavailable / empty / too_large → no Mermaid fence (never invent).
- Docs/chat Mermaid is a twin of Remotion's graph — not a second topology.

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
  component_Blob["Blob"]
  component_excelWorkbook["excelWorkbook"]
  component_excelWorkbook --> component_AlumniDraft
  component_excelWorkbook --> component_AlumniDraft
  component_excelWorkbook --> component_Blob
```

## Lifecycle

_No lifecycle diagram (`empty`)._

## Evidence

- `AlumniDraft` — `src/features/admin/excelWorkbook.ts:104`
- `Blob` — `src/features/admin/excelWorkbook.ts:52`
- `excelWorkbook` — `src/features/admin/excelWorkbook.ts:1`

## Interactive

Primary exploration is the Cursor canvas over `interactive.json`. Mermaid above is the chat/docs fallback (≤40 nodes).

Docs diagram plan: `flowchart_td`.
