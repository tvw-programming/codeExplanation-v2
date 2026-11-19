/**
 * Invariants for the published segment index
 * (run: npx --yes tsx scripts/check-segment-index.ts).
 *
 * A wrong offset here is worse than a missing one: the viewer would
 * seek confidently into the wrong file's explanation. These checks
 * assert the index tiles the video exactly — no gaps, no overlaps, no
 * missing chunk — against the stacks currently staged under
 * render-app/public/chunks/, and against a synthetic fixture so the
 * check still means something on a clean checkout.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { buildIndexForStack, stackDirs, type SegmentIndex } from "./build-segment-index";
import {
  BREAKDOWN_MIN_SECONDS,
  FPS,
  MIN_FILE_CARD_SECONDS,
  TREE_MIN_SECONDS,
  cardFramesFor,
  chapterFramesFor,
  framesToSeconds,
  segmentsForStack,
  type TimingBundle,
} from "../src/segmentTiming";

const EPSILON = 1 / FPS / 2;

function checkIndex(index: SegmentIndex): void {
  const where = `stack ${index.stack}`;
  assert.ok(index.files.length > 0, `${where}: index has no files`);

  const seen = new Set<string>();
  let cursor = 0;

  for (const file of index.files) {
    assert.ok(!seen.has(file.chunkId), `${where}: ${file.chunkId} appears twice`);
    seen.add(file.chunkId);

    assert.ok(file.filePath, `${where}: ${file.chunkId} has no filePath`);
    assert.ok(
      Math.abs(file.startSeconds - cursor) < EPSILON,
      `${where}: ${file.filePath} starts at ${file.startSeconds}s, expected ${cursor}s ` +
        "(a gap or overlap between files means every later offset is wrong)",
    );
    assert.ok(
      file.endSeconds > file.startSeconds,
      `${where}: ${file.filePath} has a non-positive span`,
    );

    // Chapters must tile their file exactly, in play order.
    let chapterCursor = file.startSeconds;
    assert.ok(file.chapters.length > 0, `${where}: ${file.filePath} has no chapters`);
    for (const chapter of file.chapters) {
      assert.ok(
        Math.abs(chapter.startSeconds - chapterCursor) < EPSILON,
        `${where}: ${file.filePath} chapter ${chapter.kind} starts at ` +
          `${chapter.startSeconds}s, expected ${chapterCursor}s`,
      );
      assert.ok(
        chapter.endSeconds > chapter.startSeconds,
        `${where}: ${file.filePath} chapter ${chapter.kind} has a non-positive span`,
      );
      chapterCursor = chapter.endSeconds;
    }
    assert.ok(
      Math.abs(chapterCursor - file.endSeconds) < EPSILON,
      `${where}: ${file.filePath} chapters end at ${chapterCursor}s but the file ` +
        `ends at ${file.endSeconds}s`,
    );

    // Every file opens on its FileCard — that is what makes an offset
    // recognisable when a human scrubs the mp4 to check it.
    assert.equal(
      file.chapters[0].kind,
      "card",
      `${where}: ${file.filePath} does not open on its FileCard`,
    );

    cursor = file.endSeconds;
  }

  assert.ok(
    Math.abs(cursor - index.totalSeconds) < EPSILON,
    `${where}: files end at ${cursor}s but totalSeconds is ${index.totalSeconds}`,
  );
  assert.equal(index.composition, `StackVideo-${index.stack}`, `${where}: wrong composition id`);
  assert.equal(index.video, `video-${index.stack}.mp4`, `${where}: wrong video filename`);
}

/** A hand-built stack, so the invariants are exercised even when no
 *  pipeline run is staged — including the minimum-duration floors and
 *  the rule that an unavailable visual contributes no chapter at all. */
function checkSynthetic(): void {
  const bundles: Record<string, TimingBundle> = {
    // Everything available, all five chapters.
    rich: {
      durationMs: 40_000,
      cardNarration: { durationMs: 9_000 },
      treeNarration: { durationMs: 5_000 },
      lifecycleNarration: { durationMs: 6_000 },
      breakdownNarration: { durationMs: 4_000 },
      visualGraph: { nodes: [] },
      lifecycleFlows: [{ id: "f1" }],
    },
    // Narration present but nothing to draw → card + code only.
    noVisuals: {
      durationMs: 12_000,
      cardNarration: { durationMs: 2_000 },
      treeNarration: { durationMs: 5_000 },
      breakdownNarration: { durationMs: 5_000 },
      lifecycleNarration: { durationMs: 5_000 },
      visualGraph: null,
      lifecycleFlows: [],
    },
  };

  const { segments, totalFrames } = segmentsForStack(
    ["rich", "noVisuals", "missing"],
    (id) => bundles[id] ?? null,
  );

  assert.equal(segments.length, 2, "a chunk with no readable bundle must be skipped");
  assert.deepEqual(
    segments[0].chapters.map((c) => c.kind),
    ["card", "tree", "lifecycle", "code", "breakdown"],
    "play order must be card -> tree -> lifecycle -> code -> breakdown",
  );
  assert.deepEqual(
    segments[1].chapters.map((c) => c.kind),
    ["card", "code"],
    "a visual with no graph/flows must contribute no chapter, not a placeholder",
  );
  assert.equal(
    segments[1].startFrame,
    segments[0].endFrame,
    "chunks must be laid out back-to-back",
  );
  assert.equal(totalFrames, segments[1].endFrame, "total must be the last chunk's end");

  // Floors: a 2s card still holds for MIN_FILE_CARD_SECONDS.
  assert.equal(
    cardFramesFor({ durationMs: 2_000 }),
    Math.ceil(MIN_FILE_CARD_SECONDS * FPS),
    "a short card must still be held for the readable minimum",
  );
  const shortFrames = chapterFramesFor({
    durationMs: 1_000,
    cardNarration: { durationMs: 500 },
    treeNarration: { durationMs: 100 },
    breakdownNarration: { durationMs: 100 },
    visualGraph: { nodes: [] },
  });
  assert.equal(shortFrames.tree, Math.ceil(TREE_MIN_SECONDS * FPS));
  assert.equal(shortFrames.breakdown, Math.ceil(BREAKDOWN_MIN_SECONDS * FPS));
  assert.ok(shortFrames.code >= 1, "code walkthrough never collapses to zero frames");

  assert.equal(framesToSeconds(45), 1.5, "frames convert to seconds at the composition fps");
}

function main(): void {
  checkSynthetic();
  console.log("check-segment-index: synthetic layout OK");

  const stacks = stackDirs();
  if (stacks.length === 0) {
    console.log("check-segment-index: no staged stacks — skipped the on-disk check.");
    return;
  }

  for (const stack of stacks) {
    // Check what is actually published, when it exists, so a stale
    // segments.json is caught rather than silently recomputed.
    const published = path.resolve(__dirname, "..", "public", "chunks", stack, "segments.json");
    const index: SegmentIndex | null = fs.existsSync(published)
      ? (JSON.parse(fs.readFileSync(published, "utf8")) as SegmentIndex)
      : buildIndexForStack(stack);
    assert.ok(index, `stack ${stack}: could not build an index`);
    checkIndex(index);
    console.log(
      `check-segment-index: ${stack} OK (${index.files.length} files, ` +
        `${index.totalSeconds.toFixed(1)}s)`,
    );
  }
}

main();
