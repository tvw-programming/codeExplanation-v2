import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useCurrentFrame } from "remotion";
import { CEV_FG_MUTED, CEV_FG_PRIMARY } from "../../visualTheme";
import { easeOutCubic, enterProgress } from "../layoutMath";
import { BROADCAST } from "./broadcastTheme";

export type LowerThirdVariant = "A" | "B" | "C" | "D";

export type LowerThirdNameplateProps = {
  /** L1 — segment / honesty / docs / breaking tag. */
  primary: string;
  /** L2 — path, keyword, or skip reason. */
  secondary?: string | null;
  variant?: LowerThirdVariant;
  accentColor?: string;
  startFrame?: number;
  reducedMotion?: boolean;
};

const VARIANT_ACCENT: Record<LowerThirdVariant, string> = {
  A: "#60a5fa",
  B: BROADCAST.assumedAmber,
  C: "#34d399",
  D: BROADCAST.urgentRed,
};

/**
 * Two-line broadcast nameplate (ref 5). Variant A = segment; B = honesty;
 * C = docs twin; D = breaking / refuse.
 */
export const LowerThirdNameplate: React.FC<LowerThirdNameplateProps> = ({
  primary,
  secondary,
  variant = "A",
  accentColor,
  startFrame = 0,
  reducedMotion = false,
}) => {
  const frame = useCurrentFrame();
  const accent = accentColor || VARIANT_ACCENT[variant];
  const progress = reducedMotion
    ? frame >= startFrame
      ? 1
      : 0
    : easeOutCubic(
        enterProgress(frame, BROADCAST.lowerThirdInFrames, startFrame),
      );
  if (progress <= 0) return null;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        opacity: progress,
        transform: reducedMotion
          ? undefined
          : `translateY(${(1 - progress) * 16}px)`,
        minWidth: 0,
      }}
    >
      <Box
        sx={{
          display: "inline-flex",
          alignSelf: "flex-start",
          bgcolor: accent,
          px: 1.25,
          py: 0.4,
          borderRadius: "2px 2px 0 0",
        }}
      >
        <Typography
          sx={{
            color: "#0b1020",
            fontSize: 11,
            fontWeight: 800,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            lineHeight: 1.1,
          }}
        >
          {primary}
        </Typography>
      </Box>
      {secondary ? (
        <Box
          sx={{
            bgcolor: BROADCAST.lowerThirdBg,
            border: `1px solid ${BROADCAST.lowerThirdBorder}`,
            borderTop: `2px solid ${accent}`,
            px: 1.5,
            py: 0.75,
            borderRadius: "0 4px 4px 4px",
          }}
        >
          <Typography
            sx={{
              color: CEV_FG_PRIMARY,
              fontSize: 15,
              fontWeight: 600,
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              lineHeight: 1.25,
            }}
          >
            {secondary}
          </Typography>
          <Typography
            sx={{
              color: CEV_FG_MUTED,
              fontSize: 10,
              letterSpacing: 0.8,
              textTransform: "uppercase",
              mt: 0.25,
            }}
          >
            {variant === "B"
              ? "Honesty"
              : variant === "C"
                ? "Docs twin"
                : variant === "D"
                  ? "Refuse"
                  : "Segment"}
          </Typography>
        </Box>
      ) : null}
    </Box>
  );
};
