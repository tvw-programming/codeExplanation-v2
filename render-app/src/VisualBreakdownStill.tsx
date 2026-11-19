import { AbsoluteFill, Audio, staticFile } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ClipNarration, VisualGraph } from "./ComponentTreeClip";
import { StackLogo } from "./StackLogo";
import {
  CEV_BG_VIDEO,
  CEV_FG_MUTED,
  CEV_FG_PRIMARY,
  type VisualTheme,
  themeForStack,
} from "./visualTheme";

const FPS = 30;
export const BREAKDOWN_MIN_SECONDS = 3;
export const BREAKDOWN_MAX_SECONDS = 5;
export const BREAKDOWN_TAIL_SECONDS = 0.3;

export function breakdownFramesFor(narration: ClipNarration | null | undefined): number {
  if (!narration) return 0;
  const spoken = narration.durationMs / 1000 + BREAKDOWN_TAIL_SECONDS;
  const clamped = Math.min(BREAKDOWN_MAX_SECONDS, Math.max(BREAKDOWN_MIN_SECONDS, spoken));
  return Math.ceil(clamped * FPS);
}

export const VisualBreakdownStill: React.FC<{
  chunkDir: string;
  visualGraph: VisualGraph;
  visualTheme?: VisualTheme | null;
  narration: ClipNarration;
  filePath?: string | null;
}> = ({ chunkDir, visualGraph, visualTheme, narration, filePath }) => {
  const isRouteTree = visualGraph.kind === "route_tree";
  const theme = visualTheme || themeForStack(isRouteTree ? "go" : "react");
  const root = (visualGraph.nodes || []).find((n) => n.id === visualGraph.rootId);
  const edgeKind = isRouteTree ? "routes_to" : "mounts";
  const childCount = (visualGraph.edges || []).filter((e) => e.kind === edgeKind).length;
  const name = filePath?.split("/").pop() || root?.label || "this file";

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <StackLogo theme={theme} />
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          px: 6,
          textAlign: "center",
        }}
      >
        <Typography sx={{ color: CEV_FG_MUTED, fontSize: 13, letterSpacing: 1, mb: 1 }}>
          INTERACTIVE BREAKDOWN
        </Typography>
        <Typography sx={{ color: CEV_FG_PRIMARY, fontSize: 28, fontWeight: 700, mb: 1 }}>
          {name}
        </Typography>
        <Typography sx={{ color: theme.primary, fontSize: 16, mb: 3 }}>
          {root?.label || (isRouteTree ? "routes" : "component")} · {childCount}{" "}
          {isRouteTree ? "route" : "mount"} edge{childCount === 1 ? "" : "s"}
        </Typography>
        <Box
          sx={{
            border: `1px solid ${theme.primary}`,
            bgcolor: `${theme.primary}18`,
            borderRadius: "10px",
            px: 3,
            py: 1.5,
          }}
        >
          <Typography sx={{ color: CEV_FG_PRIMARY, fontSize: 16 }}>
            Inspect this file&apos;s graph in chat
          </Typography>
        </Box>
      </Box>
      {narration.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
