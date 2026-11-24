/**
 * Grounded on-screen diagram descriptions — facts only from visualGraph /
 * lifecycleFlows / security flags. Never invent mounts, routes, or steps.
 */

import type { VisualGraph, SecurityFlag } from "../../ComponentTreeClip";
import type { LifecycleFlow } from "../../LifecycleFlowClip";
import { duplicateMountEdgeToOmit, mountEdgesFromRoot } from "../../structureTeaching";
import { honestyTickerLabel, type HonestyHints } from "../phaseLayoutMatrix";

export type DiagramFactTone = "default" | "assumed" | "accent";

export type DiagramFact = {
  label: string;
  tone?: DiagramFactTone;
};

export type DiagramDescription = {
  /** Lower-third primary segment tag (STRUCTURE / RUNTIME FLOW / INSPECT). */
  segmentTag: string;
  /** Secondary kicker (graph kind or flow title). */
  kicker: string;
  headline: string;
  facts: DiagramFact[];
  honestyKeyword?: string | null;
  legend?: string | null;
};

function countByKind(edges: VisualGraph["edges"]): Map<string, number> {
  const m = new Map<string, number>();
  for (const e of edges || []) {
    m.set(e.kind, (m.get(e.kind) || 0) + 1);
  }
  return m;
}

function rootLabel(graph: VisualGraph): string {
  return (
    (graph.nodes || []).find((n) => n.id === graph.rootId)?.label ||
    (graph.kind === "route_tree" ? "Routes" : "Root")
  );
}

function honestyFromGraph(graph: VisualGraph): HonestyHints {
  return {
    hasAssumed:
      (graph.edges || []).some((e) => e.assumed) ||
      (graph.nodes || []).some((n) => n.assumed),
    pathUnresolved: (graph.edges || []).some(
      (e) => e.assumed && (e.label || "").toLowerCase().includes("unresolved"),
    ),
  };
}

function segmentTagForKind(kind: string): string {
  switch (kind) {
    case "route_tree":
      return "STRUCTURE";
    case "di_graph":
      return "STRUCTURE";
    case "module_graph":
      return "STRUCTURE";
    case "crate_graph":
      return "STRUCTURE";
    case "component_tree":
    default:
      return "STRUCTURE";
  }
}

function kickerForKind(kind: string): string {
  switch (kind) {
    case "route_tree":
      return "route_tree";
    case "di_graph":
      return "di_graph";
    case "module_graph":
      return "module_graph";
    case "crate_graph":
      return "crate_graph";
    case "component_tree":
    default:
      return "component_tree";
  }
}

function topKindFacts(kindCounts: Map<string, number>, limit = 4): DiagramFact[] {
  return [...kindCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([kind, count]) => ({
      label: `${count}× ${kind}`,
      tone: "default" as const,
    }));
}

export function describeVisualGraph(
  graph: VisualGraph,
  opts?: { securityFlags?: SecurityFlag[]; inspectMode?: boolean },
): DiagramDescription {
  const root = rootLabel(graph);
  const edges = graph.edges || [];
  const nodes = graph.nodes || [];
  const kindCounts = countByKind(edges);
  const assumedEdges = edges.filter((e) => e.assumed).length;
  const assumedNodes = nodes.filter((n) => n.assumed).length;
  const honesty = honestyFromGraph(graph);
  const honestyKeyword = honestyTickerLabel(honesty);
  const flags = opts?.securityFlags?.length ?? 0;

  const facts: DiagramFact[] = [];
  facts.push(...topKindFacts(kindCounts));

  if (graph.kind === "component_tree") {
    const mounts = mountEdgesFromRoot(graph);
    const uniqueChildren = new Set(mounts.map((e) => e.to)).size;
    const headline = `${root} mounts ${uniqueChildren} unique child${
      uniqueChildren === 1 ? "" : "ren"
    } (${mounts.length} mount edge${mounts.length === 1 ? "" : "s"})`;
    if (duplicateMountEdgeToOmit(graph)) {
      facts.push({
        label: "One duplicate mount line hidden for clarity",
        tone: "accent",
      });
    }
    if (assumedEdges > 0) {
      facts.push({
        label: `${assumedEdges} assumed edge${assumedEdges === 1 ? "" : "s"}`,
        tone: "assumed",
      });
    }
    if (flags > 0) {
      facts.push({
        label: `${flags} security flag${flags === 1 ? "" : "s"} on graph`,
        tone: "accent",
      });
    }
    return {
      segmentTag: opts?.inspectMode ? "INSPECT" : segmentTagForKind(graph.kind),
      kicker: kickerForKind(graph.kind),
      headline,
      facts: facts.slice(0, 6),
      honestyKeyword,
      legend: assumedEdges > 0 ? "Dashed = assumed" : null,
    };
  }

  if (graph.kind === "route_tree") {
    const routes = edges.filter((e) => e.kind === "routes_to").length;
    const middleware = edges.filter((e) => e.kind === "middleware_before").length;
    const headline = `${root} · ${routes} route edge${routes === 1 ? "" : "s"}${
      middleware ? `, ${middleware} middleware-before` : ""
    }`;
    if (assumedEdges > 0) {
      facts.push({
        label: `${assumedEdges} assumed edge${assumedEdges === 1 ? "" : "s"}`,
        tone: "assumed",
      });
    }
    if (assumedNodes > 0) {
      facts.push({
        label: `${assumedNodes} assumed node${assumedNodes === 1 ? "" : "s"}`,
        tone: "assumed",
      });
    }
    return {
      segmentTag: opts?.inspectMode ? "INSPECT" : "STRUCTURE",
      kicker: "route_tree",
      headline,
      facts: facts.slice(0, 6),
      honestyKeyword,
      legend: assumedEdges > 0 ? "Dashed = assumed" : null,
    };
  }

  // di_graph / module_graph / crate_graph / unknown
  const headline = `${root} · ${nodes.length} node${nodes.length === 1 ? "" : "s"}, ${
    edges.length
  } edge${edges.length === 1 ? "" : "s"}`;
  if (assumedEdges > 0) {
    facts.push({
      label: `${assumedEdges} assumed edge${assumedEdges === 1 ? "" : "s"}`,
      tone: "assumed",
    });
  }
  return {
    segmentTag: opts?.inspectMode ? "INSPECT" : segmentTagForKind(graph.kind),
    kicker: kickerForKind(graph.kind),
    headline,
    facts: facts.slice(0, 6),
    honestyKeyword,
    legend: assumedEdges > 0 ? "Dashed = assumed" : null,
  };
}

/** Collapse consecutive identical middleware labels for a readable headline. */
function collapseStepSequence(steps: LifecycleFlow["steps"]): string {
  const parts: string[] = [];
  let i = 0;
  while (i < steps.length) {
    const cur = steps[i];
    let run = 1;
    while (
      i + run < steps.length &&
      steps[i + run].action === cur.action &&
      steps[i + run].label === cur.label
    ) {
      run += 1;
    }
    const label = cur.label || cur.action;
    parts.push(run > 1 ? `${label}×${run}` : label);
    i += run;
  }
  return parts.join(" → ");
}

export function describeLifecycleFlow(
  flow: LifecycleFlow | null | undefined,
  opts?: { flowIndex?: number; flowCount?: number },
): DiagramDescription {
  const steps = flow?.steps || [];
  const assumedSteps = steps.filter((s) => s.assumed).length;
  const honesty: HonestyHints = {
    hasAssumed: assumedSteps > 0 || Boolean(flow?.assumed),
    hasAllMethod: steps.some((s) => (s.action || "").toUpperCase() === "ALL"),
  };
  const honestyKeyword = honestyTickerLabel(honesty);
  const sequence = steps.length ? collapseStepSequence(steps) : "No steps extracted";
  const flowHint =
    opts?.flowCount && opts.flowCount > 1 && opts.flowIndex != null
      ? ` · flow ${opts.flowIndex + 1}/${opts.flowCount}`
      : "";

  const facts: DiagramFact[] = steps.slice(0, 6).map((s) => {
    const line =
      s.lineRange && s.lineRange.length >= 1
        ? ` L${s.lineRange[0]}${
            s.lineRange[1] != null && s.lineRange[1] !== s.lineRange[0]
              ? `–${s.lineRange[1]}`
              : ""
          }`
        : "";
    return {
      label: `${s.action}: ${s.label}${line}`,
      tone: s.assumed ? "assumed" : "default",
    };
  });

  if (assumedSteps > 0) {
    facts.push({
      label: `${assumedSteps} assumed step${assumedSteps === 1 ? "" : "s"}`,
      tone: "assumed",
    });
  }

  return {
    segmentTag: "RUNTIME FLOW",
    kicker: (flow?.title || flow?.trigger || "lifecycle") + flowHint,
    headline: sequence,
    facts: facts.slice(0, 7),
    honestyKeyword,
    legend: assumedSteps > 0 ? "Dashed pill = assumed" : null,
  };
}

/** Crawl string: path + stack + honesty only (Confirmed bundle fields). */
export function honestyCrawlText(parts: {
  stack?: string | null;
  pathShort?: string | null;
  honestyKeyword?: string | null;
  extraFact?: string | null;
}): string {
  const bits = [
    parts.stack,
    parts.pathShort,
    parts.honestyKeyword,
    parts.extraFact,
  ].filter((b): b is string => Boolean(b && String(b).trim()));
  return bits.join("  ·  ");
}
