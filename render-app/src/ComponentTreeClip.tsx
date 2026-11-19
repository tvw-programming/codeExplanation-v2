import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import { DiagramHeader } from "./DiagramHeader";
import { VisualGraphDiagram } from "./VisualGraphDiagram";
import {
  CEV_BG_VIDEO,
  CEV_FG_PRIMARY,
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
  const spoken = (narration.durationMs || 0) / 1000 + TREE_TAIL_SECONDS;
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
  const rootLabel =
    (visualGraph.nodes || []).find((n) => n.id === visualGraph.rootId)?.label ||
    (visualGraph.kind === "route_tree" ? "Routes" : "Component");

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
        titleFallback={rootLabel}
      />

      <VisualGraphDiagram
        visualGraph={visualGraph}
        theme={theme}
        securityFlags={securityFlags}
      />

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
