/**
 * Honest structure-graph teaching copy — bullets and diagram clarity only
 * from extractor nodes/edges (no invented mounts).
 */

import type { VisualGraph } from "./ComponentTreeClip";

const MOUNT_KIND = "mounts";

/**
 * When the same child node has multiple mount edges from the root, hide the
 * last edge by stable id sort so the diagram stays readable (one line per box).
 * ProfilePage → Typography (×2) keeps a single visible mount edge.
 */
export function duplicateMountEdgeToOmit(graph: VisualGraph): string | null {
  if (graph.kind !== "component_tree") return null;
  const rootId = graph.rootId;
  const mounts = (graph.edges || []).filter(
    (e) => e.kind === MOUNT_KIND && e.from === rootId,
  );
  const byTarget = new Map<string, string[]>();
  for (const e of mounts) {
    const list = byTarget.get(e.to) || [];
    list.push(e.id);
    byTarget.set(e.to, list);
  }
  for (const ids of byTarget.values()) {
    if (ids.length > 1) {
      const sorted = [...ids].sort();
      return sorted[sorted.length - 1] ?? null;
    }
  }
  return null;
}

export function mountEdgesFromRoot(graph: VisualGraph) {
  return (graph.edges || []).filter(
    (e) => e.kind === MOUNT_KIND && e.from === graph.rootId,
  );
}

/** 5–15 bullets for L3 breakdown rail — grounded in visible component_tree nodes. */
export function structureBulletsFromGraph(graph: VisualGraph): string[] {
  if (graph.kind !== "component_tree") return [];

  const nodes = new Map((graph.nodes || []).map((n) => [n.id, n]));
  const root = nodes.get(graph.rootId);
  const rootLabel = root?.label || "Root";
  const mounts = mountEdgesFromRoot(graph);

  const childOrder: string[] = [];
  const childCounts = new Map<string, number>();
  for (const e of mounts) {
    const label = nodes.get(e.to)?.label;
    if (!label) continue;
    childCounts.set(label, (childCounts.get(label) || 0) + 1);
    if (!childOrder.includes(label)) childOrder.push(label);
  }

  const bullets: string[] = [
    `${rootLabel} — component root`,
    `${mounts.length} mount edge${mounts.length === 1 ? "" : "s"} from ${rootLabel}`,
  ];

  for (const label of childOrder) {
    const count = childCounts.get(label) || 1;
    if (count > 1) {
      bullets.push(`${label} — ${count} mount records (one edge hidden on diagram)`);
    } else {
      bullets.push(`${label} — direct mount`);
    }
  }

  const dupOmit = duplicateMountEdgeToOmit(graph);
  if (dupOmit) {
    bullets.push("Diagram omits one duplicate mount line for clarity");
  }

  return bullets.slice(0, 15);
}