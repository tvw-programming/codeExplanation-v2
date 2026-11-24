import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ClipNarration, SecurityFlag, VisualGraph } from "./ComponentTreeClip";
import type { PhaseStyleMode } from "./phaseStyle";
import { AnimatedBulletList, Card3D, Split7030, TickerBar } from "./fancyLayout";
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
  duplicateMountEdgeToOmit,
  structureBulletsFromGraph,
} from "./structureTeaching";
import {
  CEV_BG_VIDEO,
  CEV_FG_MUTED,
  type VisualTheme,
  themeForStack,
  videoAccent,
} from "./visualTheme";

// Timing lives in segmentTiming.ts (shared with the viewer's segment
// index) and is re-exported here for existing importers.
import { BREAKDOWN_HOLD_SECONDS, FPS } from "./segmentTiming";
import { bulletRevealFrames, split7030Widths } from "./fancyLayout/layoutMath";
import {
  COMPOSITION_WIDTH,
  contentBandHeight,
  LEFT_PAD,
  RIGHT_SAFE,
} from "./fancyLayout/zones";

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
  const frame = useCurrentFrame();
  const isRouteTree = visualGraph.kind === "route_tree";
  const theme = visualTheme || themeForStack(isRouteTree ? "go" : "react");
  const root = (visualGraph.nodes || []).find((n) => n.id === visualGraph.rootId);
  const name = filePath?.split("/").pop() || root?.label || "this file";
  const stackKey = resolveMatrixStackKey(stackId ?? theme.stack);
  const honesty: HonestyHints = {
    hasAssumed:
      visualGraph.edges.some((e) => e.assumed) ||
      visualGraph.nodes.some((n) => n.assumed),
  };
  const patterns = resolveFancyPatterns(phaseStyle, "visualBreakdown", stackKey, honesty);
  const tickerLabel = patterns.l1 ? honestyTickerLabel(honesty) : null;
  const useMermaid = Boolean(mermaidInVideo && mermaid);
  const fancyL3 = patterns.l3 && visualGraph.kind === "component_tree";
  const omitEdgeId = fancyL3 ? duplicateMountEdgeToOmit(visualGraph) : null;
  const omitEdgeIds = omitEdgeId ? [omitEdgeId] : [];
  const teachingBullets = fancyL3 ? structureBulletsFromGraph(visualGraph) : [];
  const accent = videoAccent(theme);
  const activeBeatIndex = (narration?.beats || []).findIndex(
    (b) =>
      frame >= Math.floor(((b.startMs || 0) / 1000) * FPS) &&
      frame < Math.ceil(((b.endMs || 0) / 1000) * FPS),
  );
  const bulletReveal =
    fancyL3 && teachingBullets.length > 0
      ? bulletRevealFrames(teachingBullets.length, 8, 7)
      : [];

  const innerWidth = COMPOSITION_WIDTH - LEFT_PAD - RIGHT_SAFE;
  const l3MainWidth = split7030Widths(innerWidth, 20, 0.7).leftWidth;
  const diagramHeight = contentBandHeight(720);

  const diagram = useMermaid ? (
    <MermaidDiagram source={mermaid!} skipReason={mermaidSkipReason} />
  ) : (
    <Box sx={{ position: "relative", width: "100%", height: "100%" }}>
      <VisualGraphDiagram
        visualGraph={visualGraph}
        theme={theme}
        securityFlags={securityFlags}
        omitEdgeIds={omitEdgeIds}
        width={fancyL3 ? l3MainWidth : 1280}
        height={fancyL3 ? diagramHeight : 720}
      />
    </Box>
  );

  const summaryFooter = patterns.l4 ? (
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
      <Card3D variant="panel" durationInFrames={32} startFrame={4}>
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
  );

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={filePath}
        eyebrow="Structure graph"
        titleFallback={name}
      />
      {fancyL3 && teachingBullets.length >= 5 ? (
        <Split7030
          asideChrome
          asideTitle="Structure"
          accentColor={accent}
          main={diagram}
          aside={
            <AnimatedBulletList
              items={teachingBullets}
              revealAtFrames={bulletReveal}
              activeIndex={activeBeatIndex >= 0 ? activeBeatIndex % teachingBullets.length : null}
              accentColor={accent}
            />
          }
        />
      ) : (
        diagram
      )}
      {!fancyL3 ? summaryFooter : null}
      {tickerLabel ? (
        <TickerBar label={tickerLabel} showFromFrame={8} hideAtFrame={null} />
      ) : null}

      {narration.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
