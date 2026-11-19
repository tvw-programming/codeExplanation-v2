import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { StackLogo } from "./StackLogo";
import {
  CEV_BG_VIDEO,
  CEV_FG_MUTED,
  CEV_FG_PRIMARY,
  CEV_SECURITY,
  LOGO_HEIGHT,
  LOGO_INSET,
  type VisualTheme,
  themeForStack,
} from "./visualTheme";

export type VisualNode = {
  id: string;
  kind: string;
  label: string;
  assumed?: boolean;
  line?: number | null;
};

export type VisualEdge = {
  id: string;
  kind: string;
  from: string;
  to: string;
  assumed?: boolean;
  label?: string | null;
};

export type VisualGraph = {
  schemaVersion: number;
  kind: string;
  rootId: string;
  nodes: VisualNode[];
  edges: VisualEdge[];
};

export type ClipNarration = {
  audio: string;
  durationMs: number;
  ttsEngine?: string;
  beats?: Array<{ id?: string; spoken?: string; startMs?: number; endMs?: number }>;
};

export type SecurityFlag = {
  id: string;
  severity: string;
  ruleId: string;
  message: string;
  nodeIds?: string[];
};

const FPS = 30;
export const TREE_TAIL_SECONDS = 0.4;
export const TREE_MIN_SECONDS = 3;
export const TREE_MAX_SECONDS = 8;

export function treeFramesFor(narration: ClipNarration | null | undefined): number {
  if (!narration) return 0;
  const spoken = narration.durationMs / 1000 + TREE_TAIL_SECONDS;
  const clamped = Math.min(TREE_MAX_SECONDS, Math.max(TREE_MIN_SECONDS, spoken));
  return Math.ceil(clamped * FPS);
}

type LayoutNode = VisualNode & { x: number; y: number; depth: number };

/** Structural parent→child edges used for layout (FE mounts or BE routes). */
function structuralEdges(graph: VisualGraph): VisualEdge[] {
  const kinds = new Set([
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
  // Prefer hierarchy edges for layout; middleware drawn separately.
  return (graph.edges || []).filter((e) => kinds.has(e.kind));
}

function layoutTree(graph: VisualGraph, width: number, height: number): LayoutNode[] {
  const mounts = structuralEdges(graph);
  const children = new Map<string, string[]>();
  for (const e of mounts) {
    const list = children.get(e.from) || [];
    if (!list.includes(e.to)) list.push(e.to);
    children.set(e.from, list);
  }
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
  // Include orphans lightly under root depth
  for (const n of graph.nodes) {
    if (!visited.has(n.id)) {
      if (!levels[0]) levels[0] = [];
      levels[Math.min(1, levels.length)] = levels[Math.min(1, levels.length)] || [];
      levels[Math.min(1, levels.length)].push(n.id);
    }
  }

  const topPad = LOGO_INSET + LOGO_HEIGHT + 28;
  const bottomPad = 40;
  const rightSafe = LOGO_INSET + 80;
  const usableH = height - topPad - bottomPad;
  const usableW = width - 80 - rightSafe;
  const laid: LayoutNode[] = [];
  const depthCount = Math.max(levels.length, 1);

  levels.forEach((ids, depth) => {
    const y = topPad + (depthCount <= 1 ? usableH / 2 : (depth / (depthCount - 1)) * usableH);
    ids.forEach((id, i) => {
      const node = byId.get(id);
      if (!node) return;
      const x =
        ids.length <= 1
          ? 80 + usableW / 2
          : 80 + ((i + 0.5) / ids.length) * usableW;
      laid.push({ ...node, x, y, depth });
    });
  });
  return laid;
}

export const ComponentTreeClip: React.FC<{
  chunkDir: string;
  visualGraph: VisualGraph;
  visualTheme?: VisualTheme | null;
  securityFlags?: SecurityFlag[];
  narration?: ClipNarration | null;
}> = ({ chunkDir, visualGraph, visualTheme, securityFlags = [], narration }) => {
  const frame = useCurrentFrame();
  const theme = visualTheme || themeForStack(visualGraph.kind === "route_tree" ? "go" : "react");
  const width = 1280;
  const height = 720;
  const laid = layoutTree(visualGraph, width, height);
  const byId = new Map(laid.map((n) => [n.id, n]));
  const structure = structuralEdges(visualGraph);
  const mwEdges = (visualGraph.edges || []).filter((e) => e.kind === "middleware_before");
  const flagged = new Set(securityFlags.flatMap((f) => f.nodeIds || []));
  const isRouteTree = visualGraph.kind === "route_tree";

  const activeBeat =
    narration?.beats?.find(
      (b) =>
        frame >= Math.floor(((b.startMs || 0) / 1000) * FPS) &&
        frame < Math.floor(((b.endMs || 0) / 1000) * FPS),
    ) || null;

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <StackLogo theme={theme} />
      <Box sx={{ position: "absolute", top: 24, left: 28 }}>
        <Typography sx={{ color: CEV_FG_MUTED, fontSize: 13, letterSpacing: 1 }}>
          {isRouteTree ? "ROUTE TREE" : "COMPONENT TREE"}
        </Typography>
        <Typography sx={{ color: CEV_FG_PRIMARY, fontSize: 22, fontWeight: 600 }}>
          {byId.get(visualGraph.rootId)?.label || (isRouteTree ? "Routes" : "Component")}
        </Typography>
      </Box>

      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {structure.map((e) => {
          const from = byId.get(e.from);
          const to = byId.get(e.to);
          if (!from || !to) return null;
          return (
            <line
              key={e.id}
              x1={from.x}
              y1={from.y + 18}
              x2={to.x}
              y2={to.y - 18}
              stroke={theme.primary}
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
          // Fiber green accent for middleware_before edges.
          return (
            <line
              key={e.id}
              x1={from.x}
              y1={from.y + 18}
              x2={to.x}
              y2={to.y - 18}
              stroke={theme.secondary || theme.primary}
              strokeOpacity={e.assumed ? 0.55 : 0.9}
              strokeWidth={2}
              strokeDasharray={e.assumed ? "6 4" : "2 3"}
            />
          );
        })}
      </svg>

      {laid.map((n) => {
        const isMw = n.kind === "middleware";
        const stroke = isMw ? theme.secondary || theme.primary : theme.primary;
        return (
        <Box
          key={n.id}
          sx={{
            position: "absolute",
            left: n.x - 70,
            top: n.y - 18,
            width: 140,
            textAlign: "center",
            border: `2px solid ${stroke}`,
            bgcolor: `${stroke}30`,
            borderRadius: "8px",
            px: 1,
            py: 0.5,
            opacity: n.assumed ? 0.75 : 1,
          }}
        >
          <Typography
            sx={{
              color: CEV_FG_PRIMARY,
              fontSize: 13,
              fontWeight: 600,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
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

      {activeBeat?.spoken ? (
        <Box
          sx={{
            position: "absolute",
            left: 28,
            right: 120,
            bottom: 28,
            color: CEV_FG_PRIMARY,
            fontSize: 16,
          }}
        >
          {activeBeat.spoken}
        </Box>
      ) : null}

      {narration?.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
