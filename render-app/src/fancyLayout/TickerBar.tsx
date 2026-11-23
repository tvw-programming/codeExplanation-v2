import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useCurrentFrame } from "remotion";
import { CEV_FG_PRIMARY, CEV_SECURITY } from "../visualTheme";
import { tickerOpacity } from "./layoutMath";
import {
  COMPOSITION_WIDTH,
  TICKER_BAR_HEIGHT,
  TICKER_BOTTOM_INSET,
} from "./zones";

export type TickerBarProps = {
  /** Single honesty keyword (must match VO when wired in PR C). */
  label: string;
  /** Composition-local frame when fade-in begins. */
  showFromFrame?: number;
  /** Composition-local frame when fade-out completes; omit to hold. */
  hideAtFrame?: number | null;
  fadeFrames?: number;
  reducedMotion?: boolean;
  /** Accent for label; defaults to honesty amber. */
  accentColor?: string;
};

/**
 * L1 — bottom callout strip (not a scrolling stock ticker).
 * Sits in the caption reserve; does not cover DiagramHeader.
 */
export const TickerBar: React.FC<TickerBarProps> = ({
  label,
  showFromFrame = 0,
  hideAtFrame = null,
  fadeFrames = 10,
  reducedMotion = false,
  accentColor = CEV_SECURITY,
}) => {
  const frame = useCurrentFrame();
  const opacity = tickerOpacity(
    frame,
    showFromFrame,
    hideAtFrame,
    fadeFrames,
    reducedMotion,
  );
  if (opacity <= 0 && frame < showFromFrame) {
    return null;
  }

  return (
    <Box
      sx={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: TICKER_BOTTOM_INSET,
        height: TICKER_BAR_HEIGHT,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: "24px",
        opacity,
        pointerEvents: "none",
        zIndex: 5,
        boxSizing: "border-box",
      }}
    >
      <Box
        sx={{
          maxWidth: COMPOSITION_WIDTH - 96,
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2,
          py: 0.5,
          borderRadius: "6px",
          border: `1px solid ${accentColor}55`,
          bgcolor: "rgba(15, 20, 25, 0.92)",
        }}
      >
        <Typography
          component="span"
          sx={{
            color: accentColor,
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: 1.4,
            textTransform: "uppercase",
            flexShrink: 0,
          }}
        >
          Callout
        </Typography>
        <Typography
          component="span"
          sx={{
            color: CEV_FG_PRIMARY,
            fontSize: 13,
            fontWeight: 600,
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {label}
        </Typography>
      </Box>
    </Box>
  );
};