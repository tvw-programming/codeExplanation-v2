/**
 * Clip gating invariants for stale-bundle safety net.
 * Run: npx --yes tsx scripts/check-clip-narration-gate.ts
 */
import assert from "node:assert/strict";
import { resolvePhaseStyleFromManifest } from "../src/phaseStyle";
import {
  firstBeatSpeechEndMs,
  treeDiagramRevealFrame,
} from "../src/clipNarration";

assert.equal(resolvePhaseStyleFromManifest(null).componentTree, "fancy");
assert.equal(resolvePhaseStyleFromManifest({}).visualBreakdown, "fancy");
assert.equal(
  resolvePhaseStyleFromManifest({ componentTree: "classic" }).componentTree,
  "classic",
);

const measured = {
  durationMs: 5000,
  audio: "tree.wav",
  beats: [{ startMs: 0, speechEndMs: 2100, endMs: 2500 }],
};
assert.equal(firstBeatSpeechEndMs(measured), 2100);
assert.ok(treeDiagramRevealFrame(measured) > 30);

const stale = {
  durationMs: 5000,
  audio: "tree.wav",
  alignmentSource: "silent-hold",
  beats: [] as [],
};
assert.ok(treeDiagramRevealFrame(stale) > 0, "stale bundle with audio gates diagram");

const silent = { durationMs: 3000, audio: "", beats: [] as [] };
assert.equal(treeDiagramRevealFrame(silent), 0);

console.log("check-clip-narration-gate: ok");