# Architecture — `src/api/media.ts`

**Stack:** `react` · **Chunk:** `api-abd01dc8` · **Fidelity:** `regex`

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
  component_UploadGrant["UploadGrant"]
  component_media["media"]
  component_media --> component_UploadGrant
  component_media --> component_UploadGrant
```

## Lifecycle

_No lifecycle diagram (`empty`)._

## Evidence

- `UploadGrant` — `src/api/media.ts:50`
- `media` — `src/api/media.ts:1`

## Interactive

Primary exploration is the Cursor canvas over `interactive.json`. Mermaid above is the chat/docs fallback (≤40 nodes).

Docs diagram plan: `flowchart_td`.
