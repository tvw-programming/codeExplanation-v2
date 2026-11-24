/**
 * Invariants for fancy layout primitives (L1–L4 math).
 * Run: npx --yes tsx scripts/check-fancy-layout.ts
 */
import assert from "node:assert/strict";
import {
  bulletRevealFrames,
  card3dTransform,
  enterOffsets,
  split7030Widths,
  tickerOpacity,
} from "../src/fancyLayout/layoutMath";
import {
  CAPTION_ZONE,
  COMPOSITION_WIDTH,
  HEADER_HEIGHT,
  LEFT_PAD,
  RIGHT_SAFE,
  TICKER_EXTRA_RESERVE,
  contentBandHeight,
  contentBandHeightWithTicker,
} from "../src/fancyLayout/zones";
import {
  matrixPhaseParts,
  matrixRowKeys,
  resolveFancyPatterns,
} from "../src/fancyLayout/phaseLayoutMatrix";

const inner = COMPOSITION_WIDTH - LEFT_PAD - RIGHT_SAFE;

// --- split 70/30 ---
{
  const { leftWidth, rightWidth, gap } = split7030Widths(inner, 20, 0.7);
  assert.equal(leftWidth + rightWidth + gap, inner);
  assert.ok(leftWidth > rightWidth, "main column should be wider");
  const ratio = leftWidth / (leftWidth + rightWidth);
  assert.ok(Math.abs(ratio - 0.7) < 0.02, `ratio ${ratio}`);
}

// --- enter directions settle at origin ---
for (const direction of ["left", "top", "right"] as const) {
  const atRest = enterOffsets(60, direction, 18, 56, 0, false);
  assert.ok(Math.abs(atRest.x) < 0.01);
  assert.ok(Math.abs(atRest.y) < 0.01);
  assert.equal(atRest.opacity, 1);
  const start = enterOffsets(0, direction, 18, 56, 0, false);
  assert.equal(start.opacity, 0);
  assert.ok(
    Math.abs(start.x) + Math.abs(start.y) >= 50,
    `travel at start for ${direction}`,
  );
}

// --- reduced motion: no travel, visible at start ---
{
  const rm = enterOffsets(0, "left", 18, 56, 0, true);
  assert.equal(rm.x, 0);
  assert.equal(rm.y, 0);
  assert.equal(rm.opacity, 1);
}

// --- ticker fade windows ---
{
  assert.equal(tickerOpacity(0, 10, null, 8, false), 0);
  assert.equal(tickerOpacity(10, 10, null, 8, false), 0);
  assert.ok(tickerOpacity(14, 10, null, 8, false) > 0.4);
  assert.equal(tickerOpacity(30, 10, null, 8, false), 1);
  assert.equal(tickerOpacity(60, 10, 60, 8, false), 0);
  assert.ok(tickerOpacity(56, 10, 60, 8, false) < 0.6);
  assert.equal(tickerOpacity(20, 10, null, 8, true), 1);
}

// --- bullet stagger ---
{
  const frames = bulletRevealFrames(3, 5, 6);
  assert.deepEqual(frames, [5, 11, 17]);
}

// --- vertical safe bands ---
{
  assert.equal(contentBandHeight(720), 720 - HEADER_HEIGHT - CAPTION_ZONE);
  assert.equal(
    contentBandHeightWithTicker(720),
    720 - HEADER_HEIGHT - CAPTION_ZONE - TICKER_EXTRA_RESERVE,
  );
}

// --- matrix: classic always off ---
{
  const off = resolveFancyPatterns("classic", "chunkView", "react", { hasAssumed: true });
  assert.equal(off.l1, false);
  assert.equal(off.l2, false);
  assert.equal(off.l3, false);
  assert.equal(off.l4, false);
}

// --- matrix: fancy enables defaults ---
{
  const reactTree = resolveFancyPatterns("fancy", "componentTree", "react");
  assert.equal(reactTree.l2, true);
  assert.equal(reactTree.l2Direction, "left");
  const springChunk = resolveFancyPatterns("fancy", "chunkView", "spring");
  assert.equal(springChunk.l3, true);
}

// --- matrix shape ---
for (const row of matrixRowKeys()) {
  for (const part of matrixPhaseParts()) {
    const p = resolveFancyPatterns("fancy", part, row);
    assert.ok(typeof p.l1 === "boolean");
    assert.ok(typeof p.l4 === "boolean");
  }
}

// --- L4 matrix: only fileCard / visualBreakdown on select stacks ---
{
  assert.equal(resolveFancyPatterns("fancy", "fileCard", "react").l4, true);
  assert.equal(resolveFancyPatterns("fancy", "fileCard", "express").l4, false);
  assert.equal(resolveFancyPatterns("fancy", "visualBreakdown", "spring").l4, true);
  assert.equal(resolveFancyPatterns("fancy", "componentTree", "react").l4, false);
}

// --- L4 card3d settles shallow (readable) ---
{
  const start = card3dTransform(0, 28, 0, false);
  assert.ok(Math.abs(start.rotateYDeg) > 3, "initial tilt");
  const end = card3dTransform(80, 28, 0, false);
  assert.ok(Math.abs(end.rotateXDeg) < 3);
  assert.ok(Math.abs(end.rotateYDeg) < 1);
  assert.equal(end.opacity, 1);
  const rm = card3dTransform(0, 28, 0, true);
  assert.equal(rm.rotateXDeg, 0);
  assert.equal(rm.rotateYDeg, 0);
  assert.equal(rm.translateZPx, 0);
}

console.log("ok fancy-layout invariants");