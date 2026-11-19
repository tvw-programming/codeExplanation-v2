import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { StackLogo } from "./StackLogo";
import type { ClipNarration, SecurityFlag } from "./ComponentTreeClip";
import {
  CEV_BG_VIDEO,
  CEV_FG_MUTED,
  CEV_FG_PRIMARY,
  CEV_SECURITY,
  type VisualTheme,
  themeForStack,
} from "./visualTheme";

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

const FPS = 30;
export const LIFECYCLE_MIN_SECONDS = 4;
export const LIFECYCLE_MAX_SECONDS = 12;
export const LIFECYCLE_GAP_SECONDS = 0.3;

export function lifecycleFramesFor(narration: ClipNarration | null | undefined): number {
  if (!narration) return 0;
  const spoken = narration.durationMs / 1000 + LIFECYCLE_GAP_SECONDS;
  const clamped = Math.min(LIFECYCLE_MAX_SECONDS, Math.max(LIFECYCLE_MIN_SECONDS, spoken));
  return Math.ceil(clamped * FPS);
}

export const LifecycleFlowClip: React.FC<{
  chunkDir: string;
  flows: LifecycleFlow[];
  visualTheme?: VisualTheme | null;
  securityFlags?: SecurityFlag[];
  narration?: ClipNarration | null;
}> = ({ chunkDir, flows, visualTheme, securityFlags = [], narration }) => {
  const frame = useCurrentFrame();
  const theme = visualTheme || themeForStack("react");
  const flow = flows[0];
  const steps = flow?.steps || [];

  const activeBeatIndex = (narration?.beats || []).findIndex(
    (b) =>
      frame >= Math.floor(((b.startMs || 0) / 1000) * FPS) &&
      frame < Math.ceil(((b.endMs || 0) / 1000) * FPS),
  );
  // Map beat index onto steps (beat 0 = trigger; subsequent ≈ steps)
  const activeStep = Math.max(0, Math.min(steps.length - 1, activeBeatIndex <= 0 ? 0 : activeBeatIndex - 1));

  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <StackLogo theme={theme} />
      <Box sx={{ position: "absolute", top: 24, left: 28, right: 120 }}>
        <Typography sx={{ color: CEV_FG_MUTED, fontSize: 13, letterSpacing: 1 }}>
          LIFECYCLE
        </Typography>
        <Typography sx={{ color: CEV_FG_PRIMARY, fontSize: 22, fontWeight: 600 }}>
          {flow?.title || "handler"}
        </Typography>
      </Box>

      <Box
        sx={{
          position: "absolute",
          top: 140,
          left: 40,
          right: 120,
          display: "flex",
          alignItems: "center",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        {steps.map((step, i) => {
          const active = i === activeStep;
          return (
            <Box key={`${step.order}-${step.label}`} sx={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <Box
                sx={{
                  border: `2px ${step.assumed ? "dashed" : "solid"} ${theme.primary}`,
                  bgcolor: active ? theme.primary : `${theme.primary}22`,
                  color: active ? "#0b1020" : CEV_FG_PRIMARY,
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
                <Typography sx={{ fontSize: 13 }}>{step.label}</Typography>
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
              {i < steps.length - 1 ? (
                <Typography sx={{ color: theme.primary, fontSize: 22 }}>→</Typography>
              ) : null}
            </Box>
          );
        })}
      </Box>

      {narration?.audio ? (
        <Audio src={staticFile(`${chunkDir}/${narration.audio}`)} />
      ) : null}
    </AbsoluteFill>
  );
};
