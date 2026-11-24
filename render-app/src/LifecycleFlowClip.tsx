import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ClipNarration, SecurityFlag } from "./ComponentTreeClip";
import { DiagramHeader } from "./DiagramHeader";
import type { PhaseStyleMode } from "./phaseStyle";
import { EnterFrom, TickerBar } from "./fancyLayout";
import {
  honestyTickerLabel,
  resolveFancyPatterns,
  type HonestyHints,
} from "./fancyLayout/phaseLayoutMatrix";
import { resolveMatrixStackKey } from "./fancyLayout/stackResolve";
import {
  CEV_BG_VIDEO,
  CEV_SECURITY,
  type VisualTheme,
  themeForStack,
  videoAccent,
  videoLabelColor,
} from "./visualTheme";
import { HEADER_HEIGHT } from "./treeLayout";

export type LifecycleStep = {
  order: number;
  action: string;
  label: string;
  assumed?: boolean;
  lineRange?: number[] | null;
};

export type LifecycleFlow = {
  id: string;
  title: string;
  trigger?: string;
  steps: LifecycleStep[];
  assumed?: boolean;
};

// Timing lives in segmentTiming.ts (shared with the viewer's segment
// index) and is re-exported here for existing importers.
import { FPS } from "./segmentTiming";

export {
  LIFECYCLE_MIN_SECONDS,
  LIFECYCLE_MAX_SECONDS,
  LIFECYCLE_GAP_SECONDS,
  lifecycleFramesFor,
} from "./segmentTiming";

export const LifecycleFlowClip: React.FC<{
  chunkDir: string;
  flows: LifecycleFlow[];
  visualTheme?: VisualTheme | null;
  securityFlags?: SecurityFlag[];
  narration?: ClipNarration | null;
  filePath?: string | null;
  phaseStyle?: PhaseStyleMode;
  stackId?: string | null;
}> = ({
  chunkDir,
  flows,
  visualTheme,
  securityFlags = [],
  narration,
  filePath,
  phaseStyle = "classic",
  stackId,
}) => {
  const frame = useCurrentFrame();
  const theme = visualTheme || themeForStack("react");
  const flow = flows[0];
  const steps = flow?.steps || [];
  const accentBase = videoAccent(theme);
  const labelColor = videoLabelColor(theme);

  const activeBeatIndex = (narration?.beats || []).findIndex(
    (b) =>
      frame >= Math.floor(((b.startMs || 0) / 1000) * FPS) &&
      frame < Math.ceil(((b.endMs || 0) / 1000) * FPS),
  );
  // Map beat index onto steps (beat 0 = trigger; subsequent ≈ steps)
  const activeStep = Math.max(0, Math.min(steps.length - 1, activeBeatIndex <= 0 ? 0 : activeBeatIndex - 1));

  const stackKey = resolveMatrixStackKey(stackId ?? theme.stack);
  const honesty: HonestyHints = {
    hasAssumed: steps.some((s) => s.assumed) || Boolean(flow?.assumed),
    hasAllMethod: steps.some((s) => s.action?.toUpperCase?.() === "ALL"),
  };
  const patterns = resolveFancyPatterns(phaseStyle, "lifecycle", stackKey, honesty);
  const tickerLabel = patterns.l1 ? honestyTickerLabel(honesty) : null;

  const stepRevealFrame = (index: number): number => {
    const beatIndex = index + 1;
    const beat = narration?.beats?.[beatIndex];
    if (beat?.startMs != null) {
      return Math.floor((beat.startMs / 1000) * FPS);
    }
    return 8 + index * 14;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <DiagramHeader
        theme={theme}
        filePath={filePath}
        eyebrow="Lifecycle"
        titleFallback={flow?.title || "handler"}
      />

      {/* Center the flowchart in the remaining viewport (below header). */}
      <Box
        sx={{
          position: "absolute",
          top: HEADER_HEIGHT,
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          px: 4,
          boxSizing: "border-box",
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "12px",
            flexWrap: "wrap",
            maxWidth: 1200,
          }}
        >
          {steps.map((step, i) => {
            const active = i === activeStep;
            const accent =
              step.action === "middleware" ? theme.secondary || accentBase : accentBase;
            const pill = (
                <Box
                  sx={{
                    border: `2px ${step.assumed ? "dashed" : "solid"} ${accent}`,
                    bgcolor: active ? accent : `${accent}22`,
                    color: active
                      ? theme.stack === "javascript"
                        ? theme.secondary
                        : "#0b1020"
                      : labelColor,
                    opacity: step.assumed && !active ? 0.7 : 1,
                    borderRadius: "999px",
                    px: 2,
                    py: 1,
                    minWidth: 100,
                    textAlign: "center",
                    position: "relative",
                  }}
                >
                  <Typography sx={{ fontSize: 12, fontWeight: 700 }}>{step.action}</Typography>
                  <Typography
                    sx={{
                      fontSize: 13,
                      lineHeight: 1.2,
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      wordBreak: "break-word",
                    }}
                  >
                    {step.label}
                  </Typography>
                  {securityFlags.some((f) => f.message && step.label && f.message.includes("API")) &&
                  step.action === "api_call" ? (
                    <Box
                      sx={{
                        position: "absolute",
                        top: -6,
                        right: -6,
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        bgcolor: CEV_SECURITY,
                      }}
                    />
                  ) : null}
                </Box>
            );
            return (
              <Box key={`${step.order}-${step.label}`} sx={{ display: "flex", alignItems: "center", gap: "12px" }}>
                {patterns.l2 ? (
                  <EnterFrom
                    direction={patterns.l2Direction}
                    startFrame={stepRevealFrame(i)}
                    durationInFrames={20}
                    distancePx={72}
                  >
                    {pill}
                  </EnterFrom>
                ) : (
                  pill
                )}
                {i < steps.length - 1 ? (
                  <Typography sx={{ color: accentBase, fontSize: 22 }}>→</Typography>
                ) : null}
              </Box>
            );
          })}
        </Box>
      </Box>

      {tickerLabel ? (
        <TickerBar label={tickerLabel} showFromFrame={6} hideAtFrame={null} />
      ) : null}

      {narration?.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
