import { AbsoluteFill, Audio, staticFile } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ClipNarration, SecurityFlag, VisualGraph } from "./ComponentTreeClip";
import type { PhaseStyleMode } from "./phaseStyle";
import { Card3D, TickerBar } from "./fancyLayout";
import {
  honestyTickerLabel,
  resolveFancyPatterns,
  type HonestyHints,
} from "./fancyLayout/phaseLayoutMatrix";
import { resolveMatrixStackKey } from "./fancyLayout/stackResolve";
import { DiagramHeader } from "./DiagramHeader";
import { MermaidDiagram } from "./MermaidDiagram";
import { VisualGraphDiagram, edgeSummaryLabel } from "./VisualGraphDiagram";
import {
  CEV_BG_VIDEO,
  CEV_FG_MUTED,
  type VisualTheme,
  themeForStack,
  videoAccent,
} from "./visualTheme";

// Timing lives in segmentTiming.ts (shared with the viewer's segment
// index) and is re-exported here for existing importers.
import { BREAKDOWN_HOLD_SECONDS } from "./segmentTiming";

export {
  BREAKDOWN_HOLD_SECONDS,
  BREAKDOWN_MIN_SECONDS,
  BREAKDOWN_MAX_SECONDS,
  breakdownFramesFor,
} from "./segmentTiming";

/** @deprecated use BREAKDOWN_HOLD_SECONDS */
export const BREAKDOWN_TAIL_SECONDS = BREAKDOWN_HOLD_SECONDS;

export const VisualBreakdownStill: React.FC<{
  chunkDir: string;
  visualGraph: VisualGraph;
  visualTheme?: VisualTheme | null;
  narration: ClipNarration;
  filePath?: string | null;
  securityFlags?: SecurityFlag[];
  phaseStyle?: PhaseStyleMode;
  stackId?: string | null;
  mermaidInVideo?: boolean;
  mermaid?: string | null;
  mermaidSkipReason?: string | null;
}> = ({
  chunkDir,
  visualGraph,
  visualTheme,
  narration,
  filePath,
  securityFlags = [],
  phaseStyle = "classic",
  stackId,
  mermaidInVideo = false,
  mermaid = null,
  mermaidSkipReason = null,
}) => {
  const isRouteTree = visualGraph.kind === "route_tree";
  const theme = visualTheme || themeForStack(isRouteTree ? "go" : "react");
  const root = (visualGraph.nodes || []).find((n) => n.id === visualGraph.rootId);
  const name = filePath?.split("/").pop() || root?.label || "this file";
  const accent = videoAccent(theme);
  const stackKey = resolveMatrixStackKey(stackId ?? theme.stack);
  const honesty: HonestyHints = {
    hasAssumed:
      visualGraph.edges.some((e) => e.assumed) ||
      visualGraph.nodes.some((n) => n.assumed),
  };
  const patterns = resolveFancyPatterns(phaseStyle, "visualBreakdown", stackKey, honesty);
  const tickerLabel = patterns.l1 ? honestyTickerLabel(honesty) : null;
  const useMermaid = Boolean(mermaidInVideo && mermaid);

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={filePath}
        eyebrow="Structure graph"
        titleFallback={name}
      />
      {useMermaid ? (
        <MermaidDiagram source={mermaid!} skipReason={mermaidSkipReason} />
      ) : (
        <VisualGraphDiagram
          visualGraph={visualGraph}
          theme={theme}
          securityFlags={securityFlags}
        />
      )}
      {patterns.l4 ? (
        <Box
          sx={{
            position: "absolute",
            left: 28,
            right: 28,
            bottom: 16,
            maxWidth: 520,
            mx: "auto",
          }}
        >
          <Card3D variant="panel" durationInFrames={22}>
            <Box sx={{ px: 2, py: 1.25, textAlign: "center" }}>
              <Typography sx={{ color: CEV_FG_MUTED, fontSize: 14 }}>
                <Box component="span" sx={{ color: accent, fontWeight: 600 }}>
                  {edgeSummaryLabel(visualGraph)}
                </Box>
              </Typography>
            </Box>
          </Card3D>
        </Box>
      ) : (
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
      )}
      {tickerLabel ? (
        <TickerBar label={tickerLabel} showFromFrame={8} hideAtFrame={null} />
      ) : null}

      {narration.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
