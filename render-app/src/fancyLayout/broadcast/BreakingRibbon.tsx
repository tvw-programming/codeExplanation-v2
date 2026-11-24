import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useCurrentFrame } from "remotion";
import { BROADCAST } from "./broadcastTheme";

export type BreakingRibbonProps = {
  title?: string;
  detail?: string | null;
  startFrame?: number;
  reducedMotion?: boolean;
};

/**
 * Full-width urgency ribbon (ref 1) — F14 / skip teach only; demo-safe here.
 */
export const BreakingRibbon: React.FC<BreakingRibbonProps> = ({
  title = "CEV REFUSES TO DRAW",
  detail,
  startFrame = 0,
  reducedMotion = false,
}) => {
  const frame = useCurrentFrame();
  if (frame < startFrame) return null;
  const local = frame - startFrame;
  const flash =
    reducedMotion || local > BROADCAST.breakingFlashMax
      ? 1
      : 0.7 + 0.3 * Math.abs(Math.sin(local / 3));

  return (
    <Box
      sx={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 8,
        bgcolor: BROADCAST.urgentRed,
        opacity: flash,
        px: 2,
        py: 1,
        display: "flex",
        alignItems: "baseline",
        gap: 2,
        boxSizing: "border-box",
      }}
    >
      <Typography
        sx={{
          color: "#fff",
          fontSize: 14,
          fontWeight: 900,
          letterSpacing: 2,
          textTransform: "uppercase",
        }}
      >
        {title}
      </Typography>
      {detail ? (
        <Typography
          sx={{
            color: "rgba(255,255,255,0.9)",
            fontSize: 13,
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {detail}
        </Typography>
      ) : null}
    </Box>
  );
};
