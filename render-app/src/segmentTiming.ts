/**
 * Segment timing — the single source of truth for how long every part
 * of a chunk's video is, and therefore for where each file sits inside
 * its stack video.
 *
 * Two consumers share this module, and that sharing is the point:
 *
 *   1. FullVideo.tsx lays the <Series.Sequence>es out with it, so it
 *      decides the real frame positions in the rendered mp4.
 *   2. scripts/build-segment-index.ts reads the same bundles off disk
 *      and writes public/chunks/<stack>/segments.json, which the
 *      viewer frontend uses to seek straight to a clicked file.
 *
 * Because both go through segmentsForStack(), the published offsets
 * cannot drift from the video: changing a timing constant here moves
 * the render and the index together.
 *
 * Nothing in this file may import `remotion`, MUI or React — a plain
 * Node script (`npx tsx`) imports it with no browser or bundler.
 */

export const FPS = 30;

// ---- FileCard (see FileCard.tsx) ----
/** A card never flashes past faster than this, however short its narration. */
export const MIN_FILE_CARD_SECONDS = 6;
/** A little air after the narration ends before the walkthrough starts. */
export const FILE_CARD_TAIL_SECONDS = 0.6;

// ---- ComponentTreeClip ----
export const TREE_TAIL_SECONDS = 0.4;
export const TREE_MIN_SECONDS = 3;
export const TREE_MAX_SECONDS = 8;

// ---- LifecycleFlowClip ----
export const LIFECYCLE_MIN_SECONDS = 4;
export const LIFECYCLE_MAX_SECONDS = 12;
export const LIFECYCLE_GAP_SECONDS = 0.3;

// ---- VisualBreakdownStill ----
/** Hold the still this long after narration ends before advancing. */
export const BREAKDOWN_HOLD_SECONDS = 2;
export const BREAKDOWN_MIN_SECONDS = 3;
/** Allow spoken audio + hold without clamping the hold away. */
export const BREAKDOWN_MAX_SECONDS = 12;

/** The minimum shape each frame-count function needs. The real bundle
 *  types live beside their components; keeping these structural means
 *  this module stays free of component imports. */
export type TimedNarration = { durationMs: number } | null | undefined;

export type TimingBundle = {
  chunkId?: string;
  filePath?: string | null;
  featureName?: string | null;
  durationMs: number;
  cardNarration?: { durationMs: number } | null;
  treeNarration?: { durationMs: number } | null;
  lifecycleNarration?: { durationMs: number } | null;
  breakdownNarration?: { durationMs: number } | null;
  visualGraph?: unknown | null;
  lifecycleFlows?: unknown[] | null;
  fileOverview?: Record<string, unknown> | null;
};

/** The code walkthrough runs for exactly as long as its narration. */
export function bundleDurationInFrames(
  bundle: { durationMs: number },
  fps: number = FPS,
): number {
  return Math.max(1, Math.ceil((bundle.durationMs / 1000) * fps));
}

/** A card stays up for as long as its narration takes to read, plus a
 *  short tail, and never less than the minimum — so the viewer is
 *  neither read a summary that has left the screen nor left waiting on
 *  a card after the audio has finished. */
export function cardFramesFor(narration: TimedNarration): number {
  const spoken = narration ? narration.durationMs / 1000 + FILE_CARD_TAIL_SECONDS : 0;
  return Math.ceil(Math.max(MIN_FILE_CARD_SECONDS, spoken) * FPS);
}

export function treeFramesFor(narration: TimedNarration): number {
  if (!narration) return 0;
  const spoken = (narration.durationMs || 0) / 1000 + TREE_TAIL_SECONDS;
  const clamped = Math.min(TREE_MAX_SECONDS, Math.max(TREE_MIN_SECONDS, spoken));
  return Math.ceil(clamped * FPS);
}

export function lifecycleFramesFor(narration: TimedNarration): number {
  if (!narration) return 0;
  const spoken = (narration.durationMs || 0) / 1000 + LIFECYCLE_GAP_SECONDS;
  const clamped = Math.min(LIFECYCLE_MAX_SECONDS, Math.max(LIFECYCLE_MIN_SECONDS, spoken));
  return Math.ceil(clamped * FPS);
}

export function breakdownFramesFor(narration: TimedNarration): number {
  if (!narration) return 0;
  const spoken = (narration.durationMs || 0) / 1000;
  const total = Math.max(BREAKDOWN_MIN_SECONDS, spoken + BREAKDOWN_HOLD_SECONDS);
  return Math.ceil(Math.min(BREAKDOWN_MAX_SECONDS, total) * FPS);
}

// ===================================================================
// Chapter layout
// ===================================================================

/** The five kinds of segment a chunk can contribute, in play order. */
export type ChapterKind = "card" | "tree" | "lifecycle" | "code" | "breakdown";

export const CHAPTER_LABELS: Record<ChapterKind, string> = {
  card: "File card",
  tree: "Structure",
  lifecycle: "Lifecycle",
  code: "Code walkthrough",
  breakdown: "Breakdown",
};

export type Chapter = {
  kind: ChapterKind;
  startFrame: number;
  endFrame: number;
};

export type ChunkSegment = {
  chunkId: string;
  startFrame: number;
  /** Exclusive: the first frame of the next chunk. */
  endFrame: number;
  chapters: Chapter[];
};

/** Which optional clips this bundle actually carries.
 *
 *  This mirrors FullVideo's own gating exactly: a visual segment is
 *  rendered only when BOTH its narration audio and the thing it draws
 *  are present, and an unavailable segment is omitted outright rather
 *  than filled with a placeholder. Any change here must be made in
 *  FullVideo at the same time, which is why FullVideo calls this
 *  function instead of repeating the conditions.
 */
export function chapterFramesFor(bundle: TimingBundle): Record<ChapterKind, number> {
  const hasGraph = Boolean(bundle.visualGraph);
  const hasFlows = (bundle.lifecycleFlows?.length ?? 0) > 0;
  return {
    card: cardFramesFor(bundle.cardNarration ?? null),
    tree: bundle.treeNarration && hasGraph ? treeFramesFor(bundle.treeNarration) : 0,
    lifecycle:
      bundle.lifecycleNarration && hasFlows
        ? lifecycleFramesFor(bundle.lifecycleNarration)
        : 0,
    code: Math.max(1, bundleDurationInFrames(bundle, FPS)),
    breakdown:
      bundle.breakdownNarration && hasGraph
        ? breakdownFramesFor(bundle.breakdownNarration)
        : 0,
  };
}

/** Play order within one chunk. FullVideo pushes its sequences in this
 *  same order (card → tree → lifecycle → code → breakdown). */
export const CHAPTER_ORDER: ChapterKind[] = [
  "card",
  "tree",
  "lifecycle",
  "code",
  "breakdown",
];

/** Lays every chunk of one stack out back-to-back and reports where
 *  each one — and each chapter inside it — starts and ends.
 *
 *  `chunkIds` must be in manifest order: that is the order the stack
 *  manifest lists and therefore the order <Series> plays them in.
 *  `bundleFor` returns the parsed bundle.json for a chunk, or null if
 *  it could not be read (such a chunk is skipped, exactly as FullVideo
 *  skips a chunk whose bundle failed to load). */
export function segmentsForStack(
  chunkIds: string[],
  bundleFor: (chunkId: string) => TimingBundle | null,
): { segments: ChunkSegment[]; totalFrames: number } {
  const segments: ChunkSegment[] = [];
  let cursor = 0;

  for (const chunkId of chunkIds) {
    const bundle = bundleFor(chunkId);
    if (!bundle) continue;

    const frames = chapterFramesFor(bundle);
    const chapters: Chapter[] = [];
    const start = cursor;

    for (const kind of CHAPTER_ORDER) {
      const length = frames[kind];
      if (length <= 0) continue;
      chapters.push({ kind, startFrame: cursor, endFrame: cursor + length });
      cursor += length;
    }

    segments.push({ chunkId, startFrame: start, endFrame: cursor, chapters });
  }

  return { segments, totalFrames: cursor };
}

/** Frames → seconds, rounded to milliseconds so the JSON stays readable
 *  and a player's currentTime lands on the right frame. */
export function framesToSeconds(frames: number, fps: number = FPS): number {
  return Math.round((frames / fps) * 1000) / 1000;
}
