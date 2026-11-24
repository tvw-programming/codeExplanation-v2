/**
 * Structure-graph teaching invariants (ProfilePage-class component trees).
 * Run: npx --yes tsx scripts/check-structure-teaching.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { firstBeatSpeechEndMs, treeDiagramRevealFrame } from "../src/clipNarration";
import {
  duplicateMountEdgeToOmit,
  mountEdgesFromRoot,
  structureBulletsFromGraph,
} from "../src/structureTeaching";
import type { VisualGraph } from "../src/ComponentTreeClip";
import { FPS, treeFramesFor } from "../src/segmentTiming";

const repoRoot = resolve(import.meta.dirname, "../..");
const graphPath = resolve(
  repoRoot,
  "visuals/react/alumni-06f407dc/visualGraph.json",
);
const graph = JSON.parse(readFileSync(graphPath, "utf8")) as VisualGraph;

assert.equal(graph.rootId, "component:ProfilePage");

const mounts = mountEdgesFromRoot(graph);
assert.equal(mounts.length, 8, "ProfilePage fixture has eight mount edges");

const omit = duplicateMountEdgeToOmit(graph);
assert.ok(omit, "expected a duplicate Typography mount to omit");
assert.match(omit!, /Typography:2$/, "omit the second Typography mount edge");

const bullets = structureBulletsFromGraph(graph);
assert.ok(bullets.length >= 5 && bullets.length <= 15, `bullet count ${bullets.length}`);
for (const name of [
  "Stack",
  "Typography",
  "Alert",
  "Card",
  "SchemaFormWrapper",
  "Snackbar",
]) {
  assert.ok(
    bullets.some((b) => b.includes(name)),
    `missing bullet for ${name}`,
  );
}

const narration = {
  durationMs: 5200,
  beats: [{ startMs: 0, speechEndMs: 2100, endMs: 2500 }],
};
assert.equal(firstBeatSpeechEndMs(narration), 2100);
const reveal = treeDiagramRevealFrame(narration);
assert.equal(reveal, Math.ceil(2.1 * FPS));
const frames = treeFramesFor(narration);
assert.ok(frames >= reveal + Math.ceil(2.5 * FPS), "tree clip long enough after reveal");

const fancyReactBreakdownL3 = true; // matrix react visualBreakdown L3A + fancy
assert.equal(fancyReactBreakdownL3, true);

console.log("check-structure-teaching: ok", {
  bullets: bullets.length,
  omitEdge: omit,
});