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
  if (typeof beat.speechEndMs === "number") return beat.speechEndMs;
  if (typeof beat.endMs === "number" && typeof beat.startMs === "number") {
    return beat.endMs;
  }
  return 0;
}

/** Local frame (within the clip Sequence) when the structure diagram may appear. */
export function treeDiagramRevealFrame(
  narration: NarrationWithBeats | null | undefined,
): number {
  const ms = firstBeatSpeechEndMs(narration);
  return ms > 0 ? Math.ceil((ms / 1000) * FPS) : 0;
}