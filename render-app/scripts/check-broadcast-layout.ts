/**
 * Invariants for fixed broadcast templates + grounded diagram descriptions.
 * Run: npx --yes tsx scripts/check-broadcast-layout.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { VisualGraph } from "../src/ComponentTreeClip";
import type { LifecycleFlow } from "../src/LifecycleFlowClip";
import {
  BROADCAST,
  chooseBroadcastLayout,
  describeLifecycleFlow,
  describeVisualGraph,
  graphWidestRowFootprintRatio,
  honestyCrawlText,
  lifecycleFootprintRatio,
  split6040Widths,
} from "../src/fancyLayout/broadcast";
import { COMPOSITION_WIDTH, LEFT_PAD, RIGHT_SAFE } from "../src/fancyLayout/zones";

const repoRoot = resolve(import.meta.dirname, "../..");

const alumni = JSON.parse(
  readFileSync(resolve(repoRoot, "visuals/react/alumni-06f407dc/visualGraph.json"), "utf8"),
) as VisualGraph;

const goGraph = JSON.parse(
  readFileSync(resolve(repoRoot, "visuals/go/server-91d1514b/visualGraph.json"), "utf8"),
) as VisualGraph;

const goFlows = JSON.parse(
  readFileSync(resolve(repoRoot, "visuals/go/server-91d1514b/lifecycleFlows.json"), "utf8"),
) as LifecycleFlow[];

// --- 60/40 split ---
{
  const inner = COMPOSITION_WIDTH - LEFT_PAD - RIGHT_SAFE;
  const { leftWidth, rightWidth, gap } = split6040Widths(inner, 20);
  assert.equal(leftWidth + rightWidth + gap, inner);
  const ratio = leftWidth / (leftWidth + rightWidth);
  assert.ok(Math.abs(ratio - BROADCAST.railMainFraction) < 0.02, `ratio ${ratio}`);
}

// --- ProfilePage wide tree → band (100% + bottom) ---
{
  const ratio = graphWidestRowFootprintRatio(alumni);
  assert.ok(ratio >= BROADCAST.railFootprintMaxRatio, `alumni ratio ${ratio}`);
  assert.equal(chooseBroadcastLayout(ratio), "band");
}

// --- Compact 2-child tree → rail ---
{
  const compact: VisualGraph = {
    schemaVersion: 1,
    kind: "component_tree",
    rootId: "r",
    nodes: [
      { id: "r", kind: "component", label: "R" },
      { id: "a", kind: "component", label: "A" },
      { id: "b", kind: "component", label: "B" },
    ],
    edges: [
      { id: "1", kind: "mounts", from: "r", to: "a" },
      { id: "2", kind: "mounts", from: "r", to: "b" },
    ],
  };
  const ratio = graphWidestRowFootprintRatio(compact);
  assert.ok(ratio < BROADCAST.railFootprintMaxRatio, `compact ratio ${ratio}`);
  assert.equal(chooseBroadcastLayout(ratio), "rail");
  assert.equal(chooseBroadcastLayout(ratio, { forceBand: true }), "band");
}

// --- Go lifecycle short flow → rail ---
{
  const flow = goFlows[0];
  assert.ok(flow?.steps?.length);
  const ratio = lifecycleFootprintRatio(flow.steps);
  assert.equal(chooseBroadcastLayout(ratio), "rail");
}

// --- Grounded descriptions never invent labels ---
{
  const desc = describeVisualGraph(alumni);
  assert.equal(desc.segmentTag, "STRUCTURE");
  assert.equal(desc.kicker, "component_tree");
  assert.match(desc.headline, /ProfilePage/);
  assert.ok(desc.facts.length >= 1);
  const nodeLabels = new Set(alumni.nodes.map((n) => n.label));
  assert.ok(nodeLabels.has("ProfilePage"));
  // Headline must mention root that exists
  assert.ok(desc.headline.includes("ProfilePage"));
}

{
  const route = describeVisualGraph(goGraph);
  assert.equal(route.kicker, "route_tree");
  assert.match(route.headline, /route edge/i);
}

{
  const life = describeLifecycleFlow(goFlows[0], { flowIndex: 0, flowCount: goFlows.length });
  assert.equal(life.segmentTag, "RUNTIME FLOW");
  assert.ok(life.honestyKeyword === "assumed" || life.facts.some((f) => f.tone === "assumed"));
  for (const step of goFlows[0].steps) {
    assert.ok(
      life.headline.includes(step.label) ||
        life.facts.some((f) => f.label.includes(step.label)),
      `missing step ${step.label}`,
    );
  }
}

// --- Crawl text is honesty-only concatenation ---
{
  const crawl = honestyCrawlText({
    stack: "react",
    pathShort: "ProfilePage.tsx",
    honestyKeyword: "assumed",
    extraFact: "8× mounts",
  });
  assert.equal(crawl, "react  ·  ProfilePage.tsx  ·  assumed  ·  8× mounts");
  assert.ok(!/breaking|markets|stock/i.test(crawl));
}

console.log("ok broadcast-layout invariants");
