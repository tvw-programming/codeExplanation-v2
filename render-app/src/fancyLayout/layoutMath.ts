/**
 * Pure layout/animation helpers for fancy primitives (unit-tested via scripts/check-fancy-layout.ts).
 */

export type EnterDirection = "left" | "top" | "right";

export const HONESTY_TICKER_LABELS = [
  "assumed",
  "ALL",
  "SKIP",
  "pathResolved: false",
  "CEV_TREE_SITTER",
] as const;

export type HonestyTickerLabel = (typeof HONESTY_TICKER_LABELS)[number];

export type Split7030Columns = {
  leftWidth: number;
  rightWidth: number;
  gap: number;
};

/** 70/30 column widths with a fixed gutter; rounds to whole pixels. */
export function split7030Widths(
  totalWidth: number,
  gap: number,
  mainFraction = 0.7,
): Split7030Columns {
  if (totalWidth <= 0 || gap < 0 || mainFraction <= 0 || mainFraction >= 1) {
    throw new Error("split7030Widths: invalid inputs");
  }
  const inner = totalWidth - gap;
  const leftWidth = Math.round(inner * mainFraction);
  const rightWidth = inner - leftWidth;
  return { leftWidth, rightWidth, gap };
}

export type EnterOffsets = { x: number; y: number; opacity: number };

function clamp01(t: number): number {
  return Math.min(1, Math.max(0, t));
}

/** Progress 0→1 across [start, start+duration]. */
export function enterProgress(
  frame: number,
  durationFrames: number,
  startFrame = 0,
): number {
  if (durationFrames <= 0) return 1;
  return clamp01((frame - startFrame) / durationFrames);
}

/**
 * Directional entrance offsets for L2.
 * Reduced motion: no travel, full opacity immediately after start.
 */
export function enterOffsets(
  frame: number,
  direction: EnterDirection,
  durationFrames: number,
  distancePx: number,
  startFrame = 0,
  reducedMotion = false,
): EnterOffsets {
  const progress = enterProgress(frame, durationFrames, startFrame);
  const opacity = reducedMotion
    ? frame >= startFrame
      ? 1
      : 0
    : progress;
  if (reducedMotion) {
    return { x: 0, y: 0, opacity };
  }
  const travel = (1 - progress) * distancePx;
  switch (direction) {
    case "left":
      return { x: -travel, y: 0, opacity };
    case "right":
      return { x: travel, y: 0, opacity };
    case "top":
      return { x: 0, y: -travel, opacity };
    default: {
      const _exhaustive: never = direction;
      return _exhaustive;
    }
  }
}

/** L1 fade in/out; reduced motion uses step opacity (no fade). */
export function tickerOpacity(
  frame: number,
  showFromFrame: number,
  hideAtFrame: number | null,
  fadeFrames: number,
  reducedMotion = false,
): number {
  if (frame < showFromFrame) return 0;
  if (hideAtFrame !== null && frame >= hideAtFrame) return 0;

  if (reducedMotion) {
    if (hideAtFrame !== null && frame >= hideAtFrame - fadeFrames) return 0;
    return 1;
  }

  const fadeInEnd = showFromFrame + fadeFrames;
  if (frame < fadeInEnd) {
    return clamp01((frame - showFromFrame) / Math.max(1, fadeFrames));
  }

  if (hideAtFrame !== null) {
    const fadeOutStart = hideAtFrame - fadeFrames;
    if (frame >= fadeOutStart) {
      return clamp01((hideAtFrame - frame) / Math.max(1, fadeFrames));
    }
  }
  return 1;
}

/** Staggered reveal frames for bullet list items. */
export function bulletRevealFrames(
  itemCount: number,
  startFrame: number,
  staggerFrames: number,
): number[] {
  if (itemCount <= 0) return [];
  return Array.from({ length: itemCount }, (_, i) => startFrame + i * staggerFrames);
}

/** Per-item opacity for L3 bullets; reduced motion shows all at once. */
export function bulletItemOpacity(
  frame: number,
  revealFrame: number,
  fadeFrames: number,
  reducedMotion = false,
): number {
  if (reducedMotion) return frame >= revealFrame ? 1 : 0;
  if (frame < revealFrame) return 0;
  return clamp01((frame - revealFrame) / Math.max(1, fadeFrames));
}

export type Card3dTransform = {
  rotateXDeg: number;
  rotateYDeg: number;
  translateZPx: number;
  opacity: number;
};

/**
 * L4 — CSS 3D card pose: brief tilt-in, then a shallow readable depth (clarity-first).
 * Reduced motion: flat, no travel.
 */
export function card3dTransform(
  frame: number,
  durationFrames = 28,
  startFrame = 0,
  reducedMotion = false,
): Card3dTransform {
  if (reducedMotion) {
    return {
      rotateXDeg: 0,
      rotateYDeg: 0,
      translateZPx: 0,
      opacity: frame >= startFrame ? 1 : 0,
    };
  }
  const progress = enterProgress(frame, durationFrames, startFrame);
  const easeOut = 1 - (1 - progress) * (1 - progress);
  return {
    rotateXDeg: 9 * (1 - easeOut) + 1.25 * easeOut,
    rotateYDeg: -7 * (1 - easeOut),
    translateZPx: Math.round(14 * easeOut),
    opacity: clamp01(progress * 1.15),
  };
}