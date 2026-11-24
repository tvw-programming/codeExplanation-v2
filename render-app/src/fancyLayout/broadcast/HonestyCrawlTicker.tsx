import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useCurrentFrame } from "remotion";
import { CEV_FG_PRIMARY, CEV_SECURITY } from "../../visualTheme";
import { tickerOpacity } from "../layoutMath";
import {
  COMPOSITION_WIDTH,
  TICKER_BAR_HEIGHT,
  TICKER_BOTTOM_INSET,
} from "../zones";
import { BROADCAST } from "./broadcastTheme";

export type HonestyCrawlTickerProps = {
  /** Confirmed honesty/path/stack string only — never stock-news filler. */
  text: string;
  showFromFrame?: number;
  hideAtFrame?: number | null;
  fadeFrames?: number;
  reducedMotion?: boolean;
  accentColor?: string;
  /** Absolute bottom offset (above lower-third band when stacked). */
  bottom?: number;
};

/**
 * L1 news crawl (ref 3) — slow repeating honesty string.
 * Reduced motion: static centered hold (no crawl).
 */
export const HonestyCrawlTicker: React.FC<HonestyCrawlTickerProps> = ({
  text,
  showFromFrame = 0,
  hideAtFrame = null,
  fadeFrames = 10,
  reducedMotion = false,
  accentColor = CEV_SECURITY,
  bottom = TICKER_BOTTOM_INSET,
}) => {
  const frame = useCurrentFrame();
  const opacity = tickerOpacity(
    frame,
    showFromFrame,
    hideAtFrame,
    fadeFrames,
    reducedMotion,
  );
  if (!text.trim() || (opacity <= 0 && frame < showFromFrame)) {
    return null;
  }

  const unit = `${text.trim()}    ◆    `;
  const crawlX = reducedMotion
    ? 0
    : -((frame * BROADCAST.crawlSpeedPxPerFrame) % 720);

  return (
    <Box
      sx={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom,
        height: TICKER_BAR_HEIGHT,
        opacity,
        pointerEvents: "none",
        zIndex: 5,
        boxSizing: "border-box",
        overflow: "hidden",
        bgcolor: BROADCAST.tickerBg,
        borderTop: `1px solid ${accentColor}55`,
        display: "flex",
        alignItems: "center",
      }}
    >
      <Box
        sx={{
          flexShrink: 0,
          px: 1.5,
          height: "100%",
          display: "flex",
          alignItems: "center",
          bgcolor: accentColor,
          zIndex: 1,
          position: "relative",
        }}
      >
        <Typography
          sx={{
            color: "#0b1020",
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: 1.1,
            textTransform: "uppercase",
            whiteSpace: "nowrap",
          }}
        >
          Honesty
        </Typography>
      </Box>
      {reducedMotion ? (
        <Typography
          sx={{
            color: CEV_FG_PRIMARY,
            fontSize: 12,
            fontWeight: 600,
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            px: 2,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: COMPOSITION_WIDTH - 140,
          }}
        >
          {text}
        </Typography>
      ) : (
        <Box
          sx={{
            display: "flex",
            whiteSpace: "nowrap",
            transform: `translateX(${crawlX}px)`,
            willChange: "transform",
          }}
        >
          {[0, 1, 2, 3].map((i) => (
            <Typography
              key={i}
              component="span"
              sx={{
                color: CEV_FG_PRIMARY,
                fontSize: 12,
                fontWeight: 600,
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                px: 1,
              }}
            >
              {unit}
            </Typography>
          ))}
        </Box>
      )}
    </Box>
  );
};
