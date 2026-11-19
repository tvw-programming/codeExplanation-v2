/**
 * Layout invariants for ComponentTree (run: npx --yes tsx scripts/check-tree-layout.ts).
 */
import assert from "node:assert/strict";
import {
  CAPTION_ZONE,
  HEADER_HEIGHT,
  NODE_HEIGHT,
  NODE_WIDTH,
  layoutTree,
  nodeBox,
  rowXs,
  type LayoutGraph,
} from "../src/treeLayout";

const W = 1280;
const H = 720;

function profilePageGraph(): LayoutGraph {
  const root = "component:ProfilePage";
  const kids = ["Avatar", "UserInfo", "Stats", "Actions", "Settings"];
  return {
    kind: "component_tree",
    rootId: root,
    nodes: [
      { id: root, kind: "component", label: "ProfilePage" },
      ...kids.map((k) => ({ id: `component:${k}`, kind: "component", label: k })),
    ],
    edges: kids.map((k, i) => ({
      id: `m${i}`,
      kind: "mounts",
      from: root,
      to: `component:${k}`,
    })),
  };
}

// --- rowXs: even gutters, group centered ---
{
  const left = 48;
  const usable = 1000;
  const xs = rowXs(5, left, usable);
  assert.equal(xs.length, 5);
  const gaps: number[] = [];
  for (let i = 1; i < xs.length; i++) {
    gaps.push(xs[i] - xs[i - 1]);
  }
  for (const g of gaps) {
    assert.ok(Math.abs(g - gaps[0]) < 0.01, `uneven gutters: ${gaps}`);
  }
  const firstLeft = xs[0] - NODE_WIDTH / 2;
  const lastRight = xs[xs.length - 1] + NODE_WIDTH / 2;
  const outerLeft = firstLeft - left;
  const outerRight = left + usable - lastRight;
  assert.ok(Math.abs(outerLeft - outerRight) < 0.5, "row not centered");
  // Must NOT stretch to full usable width when packed at MIN_GUTTER
  assert.ok(lastRight - firstLeft < usable - 1, "row should pack, not stretch");
}

// --- shared Y baseline for children ---
{
  const laid = layoutTree(profilePageGraph(), W, H);
  const children = laid.filter((n) => n.depth === 1);
  assert.equal(children.length, 5);
  const y0 = children[0].y;
  for (const c of children) {
    assert.equal(c.y, y0, `uneven child Y: ${c.label}`);
  }
  // Caption clearance
  for (const c of children) {
    const box = nodeBox(c);
    assert.ok(box.bottom <= H - CAPTION_ZONE + 0.5, `caption overlap: ${c.label} bottom=${box.bottom}`);
  }
  // Header clearance
  const root = laid.find((n) => n.depth === 0)!;
  assert.ok(nodeBox(root).top >= HEADER_HEIGHT, "root overlaps header");
}

// --- nested leaves share deepest baseline ---
{
  const graph: LayoutGraph = {
    kind: "component_tree",
    rootId: "r",
    nodes: [
      { id: "r", kind: "component", label: "R" },
      { id: "a", kind: "component", label: "A" },
      { id: "b", kind: "component", label: "B" },
      { id: "c", kind: "component", label: "C" },
    ],
    edges: [
      { id: "1", kind: "mounts", from: "r", to: "a" },
      { id: "2", kind: "mounts", from: "r", to: "b" },
      { id: "3", kind: "mounts", from: "a", to: "c" },
    ],
  };
  const laid = layoutTree(graph, W, H);
  const depth1 = laid.filter((n) => n.depth === 1);
  assert.equal(new Set(depth1.map((n) => n.y)).size, 1);
  const depth2 = laid.filter((n) => n.depth === 2);
  assert.equal(depth2.length, 1);
  assert.ok(depth2[0].y > depth1[0].y);
  assert.ok(nodeBox(depth2[0]).bottom <= H - CAPTION_ZONE + 0.5);
}

// Fixed node height keeps centers on the baseline (2-line labels)
assert.equal(NODE_HEIGHT, 44);

console.log("check-tree-layout: ok");
