import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { SecurityFlag, VisualGraph } from "./ComponentTreeClip";
import {
  CEV_FG_MUTED,
  CEV_SECURITY,
  type VisualTheme,
  videoAccent,
  videoLabelColor,
} from "./visualTheme";
import {
  NODE_HEIGHT,
  NODE_WIDTH,
  drawableStructureKinds,
  layoutTree,
} from "./treeLayout";

function nodeStroke(theme: VisualTheme, kind: string): string {
  if (kind === "middleware" || kind === "signal") {
    return theme.secondary || videoAccent(theme);
  }
  return videoAccent(theme);
}

function edgeStroke(theme: VisualTheme, kind: string): string {
  if (kind === "middleware_before" || kind === "resumable_boundary" || kind === "owns_state") {
    return theme.secondary || videoAccent(theme);
  }
  return videoAccent(theme);
}

/** Static tree/route diagram shared by ComponentTreeClip and VisualBreakdownStill. */
export const VisualGraphDiagram: React.FC<{
  visualGraph: VisualGraph;
  theme: VisualTheme;
  securityFlags?: SecurityFlag[];
  width?: number;
  height?: number;
  /** Hide specific edge ids (clarity only — does not remove nodes). */
  omitEdgeIds?: string[];
}> = ({
  visualGraph,
  theme,
  securityFlags = [],
  width = 1280,
  height = 720,
  omitEdgeIds = [],
}) => {
  const omit = new Set(omitEdgeIds);
  const laid = layoutTree(visualGraph, width, height);
  const byId = new Map(laid.map((n) => [n.id, n]));
  const structureKinds = drawableStructureKinds();
  const structure = (visualGraph.edges || []).filter(
    (e) => structureKinds.has(e.kind) && !omit.has(e.id),
  );
  const mwEdges = (visualGraph.edges || []).filter((e) => e.kind === "middleware_before");
  const flagged = new Set(securityFlags.flatMap((f) => f.nodeIds || []));
  const labelColor = videoLabelColor(theme);
  const halfH = NODE_HEIGHT / 2;
  // Honesty chrome only when the graph already marks assumed facts —
  // never invent a hedge for clean edges.
  const hasAssumed =
    (visualGraph.nodes || []).some((n) => n.assumed) ||
    (visualGraph.edges || []).some((e) => e.assumed);

  return (
    <>
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {structure.map((e) => {
          const from = byId.get(e.from);
          const to = byId.get(e.to);
          if (!from || !to) return null;
          return (
            <line
              key={e.id}
              x1={from.x}
              y1={from.y + halfH}
              x2={to.x}
              y2={to.y - halfH}
              stroke={edgeStroke(theme, e.kind)}
              strokeOpacity={e.assumed ? 0.55 : 1}
              strokeWidth={2}
              strokeDasharray={e.assumed ? "6 4" : undefined}
            />
          );
        })}
        {mwEdges.map((e) => {
          const from = byId.get(e.from);
          const to = byId.get(e.to);
          if (!from || !to) return null;
          return (
            <line
              key={e.id}
              x1={from.x}
              y1={from.y + halfH}
              x2={to.x}
              y2={to.y - halfH}
              stroke={edgeStroke(theme, e.kind)}
              strokeOpacity={e.assumed ? 0.55 : 0.9}
              strokeWidth={2}
              strokeDasharray={e.assumed ? "6 4" : "2 3"}
            />
          );
        })}
      </svg>

      {laid.map((n) => {
        const stroke = nodeStroke(theme, n.kind);
        const fill =
          theme.stack === "express" ? `${theme.onDark}14` : `${stroke}30`;
        return (
          <Box
            key={n.id}
            sx={{
              position: "absolute",
              left: n.x - NODE_WIDTH / 2,
              top: n.y - NODE_HEIGHT / 2,
              width: NODE_WIDTH,
              height: NODE_HEIGHT,
              boxSizing: "border-box",
              textAlign: "center",
              border: `2px solid ${stroke}`,
              bgcolor: fill,
              borderRadius: "8px",
              px: 0.75,
              py: 0.25,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: n.assumed ? 0.75 : 1,
            }}
          >
            <Typography
              sx={{
                color: labelColor,
                fontSize: 12,
                fontWeight: 600,
                lineHeight: 1.15,
                width: "100%",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                wordBreak: "break-word",
                overflowWrap: "anywhere",
              }}
            >
              {n.label}
            </Typography>
            {flagged.has(n.id) ? (
              <Box
                sx={{
                  position: "absolute",
                  top: -8,
                  right: -8,
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  bgcolor: CEV_SECURITY,
                }}
              />
            ) : null}
          </Box>
        );
      })}
      {hasAssumed ? (
        <Typography
          sx={{
            position: "absolute",
            left: 28,
            top: 56,
            color: CEV_FG_MUTED,
            fontSize: 11,
            letterSpacing: 0.4,
            zIndex: 2,
          }}
        >
          Dashed / dimmed = assumed (extractor hedge — not invented)
        </Typography>
      ) : null}
    </>
  );
};

export function structuralEdgeCount(graph: VisualGraph): { kind: string; count: number } {
  const isRoute = graph.kind === "route_tree";
  const edgeKind = isRoute ? "routes_to" : "mounts";
  const count = (graph.edges || []).filter((e) => e.kind === edgeKind).length;
  return { kind: isRoute ? "route" : "mount", count };
}

export function edgeSummaryLabel(graph: VisualGraph): string {
  const root = (graph.nodes || []).find((n) => n.id === graph.rootId);
  const { kind, count } = structuralEdgeCount(graph);
  const unit = `${kind} edge${count === 1 ? "" : "s"}`;
  return `${root?.label || (kind === "route" ? "routes" : "component")} · ${count} ${unit}`;
}
