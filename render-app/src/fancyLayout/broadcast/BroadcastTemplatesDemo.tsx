/**
 * Studio-only composition: fixed broadcast chrome + band/rail description.
 * Not used in FullVideo.
 */
import { AbsoluteFill, Composition } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { DiagramHeader } from "../../DiagramHeader";
import { VisualGraphDiagram } from "../../VisualGraphDiagram";
import { CEV_BG_VIDEO, themeForStack } from "../../visualTheme";
import type { VisualGraph } from "../../ComponentTreeClip";
import type { LifecycleFlow } from "../../LifecycleFlowClip";
import { BroadcastDiagramFrame } from "./BroadcastDiagramFrame";
import { BreakingRibbon } from "./BreakingRibbon";
import {
  describeLifecycleFlow,
  describeVisualGraph,
  honestyCrawlText,
} from "./diagramDescription";
import {
  chooseBroadcastLayout,
  graphWidestRowFootprintRatio,
  lifecycleFootprintRatio,
} from "./layoutMode";
import { BROADCAST } from "./broadcastTheme";

const DEMO_FPS = 30;
const DEMO_DURATION = 150;

/** Compact fixture — rail candidate (few siblings). */
const RAIL_GRAPH: VisualGraph = {
  schemaVersion: 1,
  kind: "component_tree",
  rootId: "component:Root",
  nodes: [
    { id: "component:Root", kind: "component", label: "Root" },
    { id: "component:ChildA", kind: "component", label: "ChildA" },
    { id: "component:ChildB", kind: "component", label: "ChildB" },
  ],
  edges: [
    {
      id: "e1",
      kind: "mounts",
      from: "component:Root",
      to: "component:ChildA",
    },
    {
      id: "e2",
      kind: "mounts",
      from: "component:Root",
      to: "component:ChildB",
      assumed: true,
    },
  ],
};

const BAND_GRAPH: VisualGraph = {
  schemaVersion: 1,
  kind: "component_tree",
  rootId: "component:Wide",
  nodes: [
    { id: "component:Wide", kind: "component", label: "WideRoot" },
    ...Array.from({ length: 7 }, (_, i) => ({
      id: `component:N${i}`,
      kind: "component",
      label: `Node${i}`,
    })),
  ],
  edges: Array.from({ length: 7 }, (_, i) => ({
    id: `m${i}`,
    kind: "mounts",
    from: "component:Wide",
    to: `component:N${i}`,
  })),
};

const LIFE_FLOW: LifecycleFlow = {
  id: "demo",
  title: "GET /demo",
  trigger: "GET /demo",
  assumed: true,
  steps: [
    { order: 1, action: "middleware", label: "cors", assumed: true, lineRange: [10, 10] },
    { order: 2, action: "handler", label: "List", assumed: false, lineRange: [20, 20] },
    { order: 3, action: "response", label: "write", assumed: true },
  ],
};

const BroadcastTemplatesScene: React.FC<{
  variant: "rail" | "band" | "lifecycle" | "breaking";
}> = ({ variant }) => {
  const theme = themeForStack(variant === "lifecycle" ? "go" : "react");

  if (variant === "breaking") {
    return (
      <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
        <BreakingRibbon detail="skipReason: no_edges" />
        <Box sx={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Typography sx={{ color: "#9CA3AF", fontSize: 16 }}>
            Breaking ribbon demo (F14 interstitial only)
          </Typography>
        </Box>
      </AbsoluteFill>
    );
  }

  if (variant === "lifecycle") {
    const description = describeLifecycleFlow(LIFE_FLOW);
    const ratio = lifecycleFootprintRatio(LIFE_FLOW.steps);
    const mode = chooseBroadcastLayout(ratio);
    return (
      <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
        <DiagramHeader
          theme={theme}
          filePath="api/cmd/server/main.go"
          eyebrow="Lifecycle"
          segmentTag={description.segmentTag}
          liveMode="LIVE"
        />
        <BroadcastDiagramFrame
          mode={mode}
          description={description}
          pathShort="main.go"
          accentColor={theme.onDark}
          crawlText={honestyCrawlText({
            stack: "go",
            pathShort: "main.go",
            honestyKeyword: description.honestyKeyword,
          })}
          showCrawl
          diagram={
            <Box
              sx={{
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 1.5,
                px: 2,
              }}
            >
              {LIFE_FLOW.steps.map((s) => (
                <Box
                  key={s.order}
                  sx={{
                    border: `2px ${s.assumed ? "dashed" : "solid"} ${theme.onDark}`,
                    borderRadius: "999px",
                    px: 2,
                    py: 1,
                    color: "#F3F4F6",
                  }}
                >
                  <Typography sx={{ fontSize: 12, fontWeight: 700 }}>{s.action}</Typography>
                  <Typography sx={{ fontSize: 13 }}>{s.label}</Typography>
                </Box>
              ))}
            </Box>
          }
        />
      </AbsoluteFill>
    );
  }

  const graph = variant === "rail" ? RAIL_GRAPH : BAND_GRAPH;
  const description = describeVisualGraph(graph);
  const ratio = graphWidestRowFootprintRatio(graph);
  const mode = chooseBroadcastLayout(ratio);
  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={variant === "rail" ? "src/demo/Root.tsx" : "src/demo/Wide.tsx"}
        eyebrow="Component tree"
        segmentTag={description.segmentTag}
        liveMode="LIVE"
      />
      <BroadcastDiagramFrame
        mode={mode}
        description={description}
        pathShort={variant === "rail" ? "Root.tsx" : "Wide.tsx"}
        accentColor={theme.onDark}
        crawlText={honestyCrawlText({
          stack: "react",
          pathShort: variant === "rail" ? "Root.tsx" : "Wide.tsx",
          honestyKeyword: description.honestyKeyword,
        })}
        showCrawl={Boolean(description.honestyKeyword)}
        diagram={
          <VisualGraphDiagram
            visualGraph={graph}
            theme={theme}
            width={mode === "rail" ? Math.round((1280 - 48 - 120) * BROADCAST.railMainFraction) : 1280}
            height={564}
          />
        }
      />
    </AbsoluteFill>
  );
};

export const BroadcastTemplatesDemoComposition = () => (
  <>
    <Composition
      id="BroadcastTemplatesDemo-Rail"
      component={BroadcastTemplatesScene}
      durationInFrames={DEMO_DURATION}
      fps={DEMO_FPS}
      width={1280}
      height={720}
      defaultProps={{ variant: "rail" as const }}
    />
    <Composition
      id="BroadcastTemplatesDemo-Band"
      component={BroadcastTemplatesScene}
      durationInFrames={DEMO_DURATION}
      fps={DEMO_FPS}
      width={1280}
      height={720}
      defaultProps={{ variant: "band" as const }}
    />
    <Composition
      id="BroadcastTemplatesDemo-Lifecycle"
      component={BroadcastTemplatesScene}
      durationInFrames={DEMO_DURATION}
      fps={DEMO_FPS}
      width={1280}
      height={720}
      defaultProps={{ variant: "lifecycle" as const }}
    />
    <Composition
      id="BroadcastTemplatesDemo-Breaking"
      component={BroadcastTemplatesScene}
      durationInFrames={DEMO_DURATION}
      fps={DEMO_FPS}
      width={1280}
      height={720}
      defaultProps={{ variant: "breaking" as const }}
    />
  </>
);
