import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import { DiagramHeader, shortFilePath } from "./DiagramHeader";
import { MermaidDiagram } from "./MermaidDiagram";
import { VisualGraphDiagram } from "./VisualGraphDiagram";
import type { PhaseStyleMode } from "./phaseStyle";
import { EnterFrom, TickerBar } from "./fancyLayout";
import {
  BroadcastDiagramFrame,
  describeVisualGraph,
  graphBroadcastMode,
  honestyCrawlText,
} from "./fancyLayout/broadcast";
import {
  honestyTickerLabel,
  resolveFancyPatterns,
  type HonestyHints,
} from "./fancyLayout/phaseLayoutMatrix";
import { resolveMatrixStackKey } from "./fancyLayout/stackResolve";
import {
  COMPOSITION_WIDTH,
  LEFT_PAD,
  RIGHT_SAFE,
  contentBandHeight,
  contentBandHeightBroadcast,
} from "./fancyLayout/zones";
import { split6040Widths } from "./fancyLayout/broadcast/layoutMode";
import { treeDiagramRevealFrame } from "./clipNarration";

const COMPOSITION_HEIGHT = 720;
import {
  CEV_BG_VIDEO,
  CEV_FG_PRIMARY,
  type VisualTheme,
  themeForStack,
  videoAccent,
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
  beats?: Array<{
    id?: string;
    spoken?: string;
    startMs?: number;
    endMs?: number;
    speechEndMs?: number;
  }>;
};

export type SecurityFlag = {
  id: string;
  severity: string;
  ruleId: string;
  message: string;
  nodeIds?: string[];
};

// Timing lives in segmentTiming.ts (shared with the viewer's segment
// index) and is re-exported here for existing importers.
import { FPS } from "./segmentTiming";

export {
  TREE_TAIL_SECONDS,
  TREE_MIN_SECONDS,
  TREE_MAX_SECONDS,
  treeFramesFor,
} from "./segmentTiming";

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
  phaseStyle?: PhaseStyleMode;
  stackId?: string | null;
  mermaidInVideo?: boolean;
  mermaid?: string | null;
  mermaidSkipReason?: string | null;
}> = ({
  chunkDir,
  visualGraph,
  visualTheme,
  securityFlags = [],
  narration,
  filePath,
  phaseStyle = "classic",
  stackId,
  mermaidInVideo = false,
  mermaid = null,
  mermaidSkipReason = null,
}) => {
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

  const diagramRevealFrame = treeDiagramRevealFrame(narration);
  const showDiagram = frame >= diagramRevealFrame;

  const stackKey = resolveMatrixStackKey(stackId ?? theme.stack);
  const honesty: HonestyHints = {
    hasAssumed:
      visualGraph.edges.some((e) => e.assumed) ||
      visualGraph.nodes.some((n) => n.assumed),
    pathUnresolved: visualGraph.edges.some(
      (e) => e.assumed && (e.label || "").toLowerCase().includes("unresolved"),
    ),
  };
  const patterns = resolveFancyPatterns(phaseStyle, "componentTree", stackKey, honesty);
  const tickerLabel = patterns.l1 ? honestyTickerLabel(honesty) : null;
  const useMermaid = Boolean(mermaidInVideo && mermaid);
  const fancy = phaseStyle === "fancy";
  const accent = videoAccent(theme);
  const description = describeVisualGraph(visualGraph, { securityFlags });
  const layoutMode = graphBroadcastMode(visualGraph, { forceBand: useMermaid });
  const liveMode = narration?.beats?.length ? "LIVE" : "REPLAY";
  const pathShort = shortFilePath(filePath) || rootLabel;
  const crawl = honestyCrawlText({
    stack: theme.stack,
    pathShort,
    honestyKeyword: description.honestyKeyword,
    extraFact: description.facts[0]?.label,
  });

  const diagramHeight = fancy
    ? contentBandHeightBroadcast(COMPOSITION_HEIGHT)
    : patterns.l2
      ? contentBandHeight(COMPOSITION_HEIGHT)
      : COMPOSITION_HEIGHT;
  const innerWidth = COMPOSITION_WIDTH - LEFT_PAD - RIGHT_SAFE;
  const railMainWidth = split6040Widths(innerWidth, 20).leftWidth;
  const diagramWidth =
    fancy && layoutMode === "rail" && !useMermaid ? railMainWidth : 1280;

  const diagram = useMermaid ? (
    <MermaidDiagram source={mermaid!} skipReason={mermaidSkipReason} />
  ) : (
    <VisualGraphDiagram
      visualGraph={visualGraph}
      theme={theme}
      securityFlags={securityFlags}
      width={diagramWidth}
      height={diagramHeight}
    />
  );

  const wrappedDiagram =
    showDiagram && patterns.l2 ? (
      <EnterFrom
        direction={patterns.l2Direction}
        fillBelowHeader={!fancy}
        durationInFrames={26}
        distancePx={96}
        startFrame={diagramRevealFrame}
        style={
          fancy
            ? { position: "absolute", inset: 0, width: "100%", height: "100%" }
            : undefined
        }
      >
        {diagram}
      </EnterFrom>
    ) : showDiagram ? (
      diagram
    ) : null;

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={filePath}
        eyebrow={eyebrowFor(visualGraph.kind)}
        titleFallback={rootLabel}
        segmentTag={fancy ? description.segmentTag : null}
        liveMode={fancy ? liveMode : null}
      />

      {fancy ? (
        <BroadcastDiagramFrame
          mode={layoutMode}
          description={description}
          diagram={wrappedDiagram}
          pathShort={pathShort}
          accentColor={accent}
          crawlText={crawl}
          showCrawl={Boolean(tickerLabel || description.honestyKeyword)}
        />
      ) : (
        <>
          {wrappedDiagram}
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
          {tickerLabel ? (
            <TickerBar label={tickerLabel} showFromFrame={6} hideAtFrame={null} />
          ) : null}
        </>
      )}

      {narration?.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
