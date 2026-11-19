import { AbsoluteFill, Audio, staticFile } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ClipNarration, SecurityFlag, VisualGraph } from "./ComponentTreeClip";
import { DiagramHeader } from "./DiagramHeader";
import { VisualGraphDiagram, edgeSummaryLabel } from "./VisualGraphDiagram";
import {
  CEV_BG_VIDEO,
  CEV_FG_MUTED,
  type VisualTheme,
  themeForStack,
  videoAccent,
} from "./visualTheme";

const FPS = 30;
/** Hold the still this long after narration ends before advancing. */
export const BREAKDOWN_HOLD_SECONDS = 2;
export const BREAKDOWN_MIN_SECONDS = 3;
/** Allow spoken audio + hold without clamping the hold away. */
export const BREAKDOWN_MAX_SECONDS = 12;
/** @deprecated use BREAKDOWN_HOLD_SECONDS */
export const BREAKDOWN_TAIL_SECONDS = BREAKDOWN_HOLD_SECONDS;

export function breakdownFramesFor(narration: ClipNarration | null | undefined): number {
  if (!narration) return 0;
  const spoken = (narration.durationMs || 0) / 1000;
  const total = Math.max(BREAKDOWN_MIN_SECONDS, spoken + BREAKDOWN_HOLD_SECONDS);
  return Math.ceil(Math.min(BREAKDOWN_MAX_SECONDS, total) * FPS);
}

export const VisualBreakdownStill: React.FC<{
  chunkDir: string;
  visualGraph: VisualGraph;
  visualTheme?: VisualTheme | null;
  narration: ClipNarration;
  filePath?: string | null;
  securityFlags?: SecurityFlag[];
}> = ({ chunkDir, visualGraph, visualTheme, narration, filePath, securityFlags = [] }) => {
  const isRouteTree = visualGraph.kind === "route_tree";
  const theme = visualTheme || themeForStack(isRouteTree ? "go" : "react");
  const root = (visualGraph.nodes || []).find((n) => n.id === visualGraph.rootId);
  const name = filePath?.split("/").pop() || root?.label || "this file";
  const accent = videoAccent(theme);

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={filePath}
        eyebrow="Structure graph"
        titleFallback={name}
      />
      <VisualGraphDiagram
        visualGraph={visualGraph}
        theme={theme}
        securityFlags={securityFlags}
      />
      <Box
        sx={{
          position: "absolute",
          left: 28,
          right: 28,
          bottom: 20,
          textAlign: "center",
        }}
      >
        <Typography sx={{ color: CEV_FG_MUTED, fontSize: 14 }}>
          <Box component="span" sx={{ color: accent, fontWeight: 600 }}>
            {edgeSummaryLabel(visualGraph)}
          </Box>
        </Typography>
      </Box>
      {narration.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
