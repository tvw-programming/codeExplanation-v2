import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { DiagramHeader } from "./DiagramHeader";
import {
  CEV_BG_VIDEO,
  CEV_FG_PRIMARY,
  CEV_SECURITY,
  type VisualTheme,
  themeForStack,
  videoAccent,
  videoLabelColor,
} from "./visualTheme";
import {
  NODE_HEIGHT,
  NODE_WIDTH,
  drawableStructureKinds,
  layoutTree,
} from "./treeLayout";

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

function eyebrowFor(kind: string): string {
  switch (kind) {
    case "route_tree":
      return "Route tree";
    case "di_graph":
      return "DI graph";
    case "module_graph":
      return "Module graph";
    case "crate_graph":
      return "Crate graph";
    default:
      return "Component tree";
  }
}

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

export const ComponentTreeClip: React.FC<{
  chunkDir: string;
  visualGraph: VisualGraph;
  visualTheme?: VisualTheme | null;
  securityFlags?: SecurityFlag[];
  narration?: ClipNarration | null;
  filePath?: string | null;
}> = ({ chunkDir, visualGraph, visualTheme, securityFlags = [], narration, filePath }) => {
  const frame = useCurrentFrame();
  const theme =
    visualTheme ||
    themeForStack(visualGraph.kind === "route_tree" ? "go" : "react");
  const width = 1280;
  const height = 720;
  const laid = layoutTree(visualGraph, width, height);
  const byId = new Map(laid.map((n) => [n.id, n]));
  const structureKinds = drawableStructureKinds();
  const structure = (visualGraph.edges || []).filter((e) => structureKinds.has(e.kind));
  const mwEdges = (visualGraph.edges || []).filter((e) => e.kind === "middleware_before");
  const flagged = new Set(securityFlags.flatMap((f) => f.nodeIds || []));
  const labelColor = videoLabelColor(theme);
  const halfH = NODE_HEIGHT / 2;

  const activeBeat =
    narration?.beats?.find(
      (b) =>
        frame >= Math.floor(((b.startMs || 0) / 1000) * FPS) &&
        frame < Math.floor(((b.endMs || 0) / 1000) * FPS),
    ) || null;

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={filePath}
        eyebrow={eyebrowFor(visualGraph.kind)}
        titleFallback={byId.get(visualGraph.rootId)?.label}
      />

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
              px: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: n.assumed ? 0.75 : 1,
            }}
          >
            <Typography
              sx={{
                color: labelColor,
                fontSize: 13,
                fontWeight: 600,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                width: "100%",
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
            bottom: 20,
            color: CEV_FG_PRIMARY,
            fontSize: 16,
            lineHeight: 1.35,
            maxHeight: 52,
            overflow: "hidden",
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
