/**
 * Measured-beat narration helpers shared by tree / breakdown clips.
 * Uses Piper-aligned `speechEndMs` when present (render_pipeline beat_meta).
 */

import { FPS } from "./segmentTiming";

export type MeasuredBeat = {
  id?: string;
  spoken?: string;
  startMs?: number;
  endMs?: number;
  speechEndMs?: number;
};

export type NarrationWithBeats = {
  durationMs?: number;
  audio?: string;
  alignmentSource?: string;
  beats?: MeasuredBeat[];
};

/** Clip has beat timing usable for diagram gating / L3 breakdown (not silent-hold). */
export function hasClipMeasuredBeats(
  narration: NarrationWithBeats | null | undefined,
): boolean {
  if (!narration) return false;
  if (narration.alignmentSource === "silent-hold") return false;
  const beats = narration.beats;
  if (!beats?.length) return false;
  const first = beats[0];
  if (typeof first.speechEndMs === "number" && first.speechEndMs > 0) return true;
  if (
    typeof first.endMs === "number" &&
    typeof first.startMs === "number" &&
    first.endMs > first.startMs
  ) {
    return true;
  }
  return false;
}

/** End of spoken audio for beat 0 (not including pause_after padding). */
export function firstBeatSpeechEndMs(
  narration: NarrationWithBeats | null | undefined,
): number {
  const beat = narration?.beats?.[0];
  if (!beat) return 0;
  if (typeof beat.speechEndMs === "number" && beat.speechEndMs > 0) {
    return beat.speechEndMs;
  }
  if (typeof beat.endMs === "number" && typeof beat.startMs === "number") {
    return beat.endMs;
  }
  return 0;
}

const TREE_GATE_FALLBACK_MAX_MS = 6500;
const TREE_GATE_FALLBACK_MIN_MS = 1200;

/**
 * Stale staged bundles may ship tree.wav + durationMs but lose beats[].
 * Gate the diagram for roughly the first orientation sentence instead of frame 0.
 */
function treeGateFallbackMs(narration: NarrationWithBeats): number {
  const duration = narration.durationMs ?? 0;
  if (!narration.audio || duration < 500) return 0;
  return Math.min(
    TREE_GATE_FALLBACK_MAX_MS,
    Math.max(TREE_GATE_FALLBACK_MIN_MS, Math.round(duration * 0.36)),
  );
}

/** Local frame (within the clip Sequence) when the structure diagram may appear. */
export function treeDiagramRevealFrame(
  narration: NarrationWithBeats | null | undefined,
): number {
  if (!narration) return 0;
  const ms = firstBeatSpeechEndMs(narration);
  const gateMs = ms > 0 ? ms : treeGateFallbackMs(narration);
  return gateMs > 0 ? Math.ceil((gateMs / 1000) * FPS) : 0;
}