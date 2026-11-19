/**
 * Shared ComponentTree layout engine.
 *
 * Rules:
 * - Nodes at the same depth share one Y baseline.
 * - Children are packed with even gutters and the whole row is
 *   center-aligned in the usable band (not stretched edge-to-edge).
 * - Bottom caption zone stays clear of node boxes.
 * - Top header + logo safe zones stay clear of node boxes.
 */

import { LOGO_INSET } from "./visualTheme";

export type LayoutGraphNode = {
  id: string;
  kind: string;
  label: string;
  assumed?: boolean;
  line?: number | null;
};

export type LayoutGraphEdge = {
  id: string;
  kind: string;
  from: string;
  to: string;
  assumed?: boolean;
  label?: string | null;
};

export type LayoutGraph = {
  kind: string;
  rootId: string;
  nodes: LayoutGraphNode[];
  edges: LayoutGraphEdge[];
};

export type LaidOutNode = LayoutGraphNode & {
  x: number;
  y: number;
  depth: number;
};

/** Fixed node chrome used by Remotion + layout math (must stay in sync). */
export const NODE_WIDTH = 140;
/** Tall enough for two-line child labels without awkward ellipsis. */
export const NODE_HEIGHT = 44;
/** Minimum gap between sibling box edges. */
export const MIN_GUTTER = 16;
/** Reserved band for narration caption at the bottom of 1280×720. */
export const CAPTION_ZONE = 80;
/** AppBar-style file header height (see DiagramHeader). */
export const HEADER_HEIGHT = 48;
/** Left content inset. */
export const LEFT_PAD = 48;
/** Right content inset (logo safe zone). */
export const RIGHT_SAFE = LOGO_INSET + 96;

/** Edge kinds that define parent→child hierarchy for a given graph kind. */
export function hierarchyEdgeKinds(graphKind: string): Set<string> {
  switch (graphKind) {
    case "route_tree":
      return new Set(["routes_to"]);
    case "di_graph":
      return new Set(["injects", "routes_to"]);
    case "module_graph":
      return new Set(["imports", "provides"]);
    case "crate_graph":
      return new Set(["depends_on", "imports"]);
    case "signal_graph":
      return new Set(["owns_state"]);
    case "component_tree":
    default:
      // Mounts/providers define the tree. Binding / signal / boundary edges
      // are also downward from the component root in our builders.
      return new Set([
        "mounts",
        "provides",
        "output_bind",
        "owns_state",
        "resumable_boundary",
        "injects",
      ]);
  }
}

/**
 * Edges drawn as structure lines (excludes middleware, which is accent-only).
 * Broader than hierarchy — used for SVG strokes only.
 */
export function drawableStructureKinds(): Set<string> {
  return new Set([
    "mounts",
    "provides",
    "routes_to",
    "imports",
    "injects",
    "depends_on",
    "input_bind",
    "output_bind",
    "owns_state",
    "resumable_boundary",
  ]);
}

/**
 * Build parent→child adjacency for layout.
 * Edges that point *toward* the root (e.g. Angular input_bind, React
 * provider→root) are reversed so those nodes become depth-1 children.
 */
export function buildChildrenMap(
  graph: LayoutGraph,
): Map<string, string[]> {
  const kinds = hierarchyEdgeKinds(graph.kind);
  const edges = (graph.edges || []).filter((e) => kinds.has(e.kind));
  // Also fold input_bind (hook → root) into hierarchy as root → hook.
  const inputBinds = (graph.edges || []).filter((e) => e.kind === "input_bind");

  const children = new Map<string, string[]>();
  const add = (from: string, to: string) => {
    if (from === to) return;
    const list = children.get(from) || [];
    if (!list.includes(to)) list.push(to);
    children.set(from, list);
  };

  for (const e of edges) {
    // provides may be provider→root (React) or root→selector (Angular).
    // Orient away from root when the edge targets the root.
    if (e.to === graph.rootId && e.from !== graph.rootId) {
      add(graph.rootId, e.from);
    } else {
      add(e.from, e.to);
    }
  }
  for (const e of inputBinds) {
    if (e.to === graph.rootId) {
      add(graph.rootId, e.from);
    } else {
      add(e.from, e.to);
    }
  }
  return children;
}

/** Even gutters; pack the row and center the group in [left, left+usableW]. */
export function rowXs(
  count: number,
  left: number,
  usableW: number,
  nodeWidth: number = NODE_WIDTH,
  minGutter: number = MIN_GUTTER,
): number[] {
  if (count <= 0) return [];
  if (count === 1) return [left + usableW / 2];

  const maxContent = usableW;
  // Prefer even gutters at MIN_GUTTER; if that overflows, shrink gutter (floor 4).
  let gutter = minGutter;
  let span = count * nodeWidth + (count - 1) * gutter;
  if (span > maxContent) {
    gutter = Math.max(4, (maxContent - count * nodeWidth) / (count - 1));
    span = count * nodeWidth + (count - 1) * gutter;
  }
  const start = left + (usableW - span) / 2;
  const xs: number[] = [];
  for (let i = 0; i < count; i++) {
    xs.push(start + i * (nodeWidth + gutter) + nodeWidth / 2);
  }
  return xs;
}

export function layoutTree(
  graph: LayoutGraph,
  width: number,
  height: number,
): LaidOutNode[] {
  const children = buildChildrenMap(graph);
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const rootId = graph.rootId;

  const levels: string[][] = [];
  const visited = new Set<string>();
  const queue: Array<{ id: string; depth: number }> = [{ id: rootId, depth: 0 }];
  while (queue.length) {
    const { id, depth } = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    if (!levels[depth]) levels[depth] = [];
    levels[depth].push(id);
    for (const child of children.get(id) || []) {
      queue.push({ id: child, depth: depth + 1 });
    }
  }

  // Orphans (e.g. disconnected nodes) sit on the first child row.
  const orphanDepth = Math.min(1, Math.max(levels.length - 1, 0));
  for (const n of graph.nodes) {
    if (visited.has(n.id)) continue;
    if (!levels[orphanDepth]) levels[orphanDepth] = [];
    levels[orphanDepth].push(n.id);
    visited.add(n.id);
  }

  const topPad = HEADER_HEIGHT + 16;
  const bottomPad = CAPTION_ZONE;
  const usableH = Math.max(NODE_HEIGHT, height - topPad - bottomPad);
  const usableW = Math.max(NODE_WIDTH, width - LEFT_PAD - RIGHT_SAFE);
  const left = LEFT_PAD;
  const depthCount = Math.max(levels.length, 1);
  const laid: LaidOutNode[] = [];

  levels.forEach((ids, depth) => {
    // Shared baseline for the entire depth row.
    const y =
      topPad +
      NODE_HEIGHT / 2 +
      (depthCount <= 1
        ? (usableH - NODE_HEIGHT) / 2
        : (depth / (depthCount - 1)) * (usableH - NODE_HEIGHT));
    const xs = rowXs(ids.length, left, usableW);
    ids.forEach((id, i) => {
      const node = byId.get(id);
      if (!node) return;
      laid.push({ ...node, x: xs[i], y, depth });
    });
  });
  return laid;
}

/** Axis-aligned box for a laid-out node (top-left origin). */
export function nodeBox(n: { x: number; y: number }): {
  left: number;
  top: number;
  right: number;
  bottom: number;
} {
  return {
    left: n.x - NODE_WIDTH / 2,
    top: n.y - NODE_HEIGHT / 2,
    right: n.x + NODE_WIDTH / 2,
    bottom: n.y + NODE_HEIGHT / 2,
  };
}
