/**
 * Fixed template picker: band (100% diagram + bottom description) vs
 * rail (≈60% diagram + ≈40% side description). Geometry only — not matrix chrome.
 */
import {
  buildChildrenMap,
  LEFT_PAD,
  MIN_GUTTER,
  NODE_WIDTH,
  RIGHT_SAFE,
  type LayoutGraph,
} from "../../treeLayout";
import { COMPOSITION_WIDTH } from "../zones";
import { BROADCAST } from "./broadcastTheme";
import { split7030Widths } from "../layoutMath";

export type BroadcastLayoutMode = "band" | "rail";

export type LifecycleStepLike = {
  label: string;
  action?: string;
};

/** Widest hierarchy row footprint as a fraction of usable inner width. */
export function graphWidestRowFootprintRatio(
  graph: LayoutGraph,
  compositionWidth = COMPOSITION_WIDTH,
): number {
  const children = buildChildrenMap(graph);
  let maxCount = 1;
  for (const ids of children.values()) {
    maxCount = Math.max(maxCount, ids.length);
  }
  // Also count root-only single-node graphs.
  maxCount = Math.max(maxCount, 1);
  const usable = Math.max(1, compositionWidth - LEFT_PAD - RIGHT_SAFE);
  const span =
    maxCount * NODE_WIDTH + Math.max(0, maxCount - 1) * MIN_GUTTER;
  return span / usable;
}

/** Horizontal pill-row estimate for lifecycle steppers. */
export function lifecycleFootprintRatio(
  steps: LifecycleStepLike[],
  compositionWidth = COMPOSITION_WIDTH,
): number {
  if (!steps.length) return 1;
  const usable = Math.max(1, compositionWidth - LEFT_PAD - RIGHT_SAFE);
  const pillW = (label: string) =>
    Math.min(200, Math.max(100, Math.round(label.length * 7.2 + 36)));
  const arrowGap = 28;
  let total = 0;
  steps.forEach((s, i) => {
    total += pillW(s.label || s.action || "step");
    if (i < steps.length - 1) total += arrowGap;
  });
  return total / usable;
}

export function chooseBroadcastLayout(
  footprintRatio: number,
  opts?: { forceBand?: boolean },
): BroadcastLayoutMode {
  if (opts?.forceBand) return "band";
  if (footprintRatio < BROADCAST.railFootprintMaxRatio) return "rail";
  return "band";
}

/** 60/40 column widths (broadcast rail). */
export function split6040Widths(totalWidth: number, gap = 20) {
  return split7030Widths(totalWidth, gap, BROADCAST.railMainFraction);
}

export function graphBroadcastMode(
  graph: LayoutGraph,
  opts?: { forceBand?: boolean; compositionWidth?: number },
): BroadcastLayoutMode {
  const ratio = graphWidestRowFootprintRatio(
    graph,
    opts?.compositionWidth ?? COMPOSITION_WIDTH,
  );
  return chooseBroadcastLayout(ratio, { forceBand: opts?.forceBand });
}

export function lifecycleBroadcastMode(
  steps: LifecycleStepLike[],
  opts?: { forceBand?: boolean; compositionWidth?: number },
): BroadcastLayoutMode {
  const ratio = lifecycleFootprintRatio(
    steps,
    opts?.compositionWidth ?? COMPOSITION_WIDTH,
  );
  return chooseBroadcastLayout(ratio, { forceBand: opts?.forceBand });
}
