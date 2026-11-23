import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useCurrentFrame } from "remotion";
import { CEV_FG_MUTED, CEV_FG_PRIMARY } from "../visualTheme";
import { bulletItemOpacity, bulletRevealFrames } from "./layoutMath";

export type AnimatedBulletListProps = {
  items: string[];
  /** Explicit per-item reveal frame (parent-local); overrides stagger when set. */
  revealAtFrames?: number[];
  startFrame?: number;
  staggerFrames?: number;
  itemFadeFrames?: number;
  reducedMotion?: boolean;
  /** Highlight the active teaching beat. */
  activeIndex?: number | null;
  accentColor?: string;
};

/**
 * Right-rail bullets for L3; text must restate Confirmed facts (wired in PR C).
 */
export const AnimatedBulletList: React.FC<AnimatedBulletListProps> = ({
  items,
  revealAtFrames,
  startFrame = 6,
  staggerFrames = 8,
  itemFadeFrames = 6,
  reducedMotion = false,
  activeIndex = null,
  accentColor = "#60a5fa",
}) => {
  const frame = useCurrentFrame();
  const frames =
    revealAtFrames && revealAtFrames.length === items.length
      ? revealAtFrames
      : bulletRevealFrames(items.length, startFrame, staggerFrames);

  return (
    <Box
      component="ul"
      sx={{
        listStyle: "none",
        m: 0,
        p: 0,
        display: "flex",
        flexDirection: "column",
        gap: 1.25,
      }}
    >
      {items.map((text, i) => {
        const opacity = bulletItemOpacity(
          frame,
          frames[i] ?? startFrame,
          itemFadeFrames,
          reducedMotion,
        );
        const active = activeIndex === i;
        return (
          <Box
            component="li"
            key={`${i}-${text.slice(0, 24)}`}
            sx={{
              opacity,
              display: "flex",
              gap: 1,
              alignItems: "flex-start",
              borderLeft: active ? `3px solid ${accentColor}` : "3px solid transparent",
              pl: 1,
            }}
          >
            <Typography
              component="span"
              sx={{
                color: accentColor,
                fontSize: 12,
                fontWeight: 700,
                lineHeight: 1.4,
                flexShrink: 0,
                mt: "1px",
              }}
            >
              •
            </Typography>
            <Typography
              component="span"
              sx={{
                color: active ? CEV_FG_PRIMARY : CEV_FG_MUTED,
                fontSize: 12,
                lineHeight: 1.45,
                fontWeight: active ? 600 : 400,
              }}
            >
              {text}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
};