import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useCurrentFrame } from "remotion";
import { BROADCAST } from "./broadcastTheme";

export type LiveBadgeProps = {
  /** LIVE when measured-beat narration is present; else REPLAY. */
  mode?: "LIVE" | "REPLAY";
  reducedMotion?: boolean;
};

/**
 * News-desk LIVE / REPLAY chip — sits in the header right slot (beside logo).
 */
export const LiveBadge: React.FC<LiveBadgeProps> = ({
  mode = "LIVE",
  reducedMotion = false,
}) => {
  const frame = useCurrentFrame();
  const pulse =
    reducedMotion || mode === "REPLAY"
      ? 1
      : 0.55 + 0.45 * Math.abs(Math.sin(frame / 18));

  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        px: 1,
        py: 0.35,
        borderRadius: "4px",
        bgcolor: mode === "LIVE" ? BROADCAST.liveRed : "rgba(255,255,255,0.12)",
        boxShadow: mode === "LIVE" ? `0 0 0 1px ${BROADCAST.liveRed}88` : "none",
        flexShrink: 0,
      }}
    >
      <Box
        sx={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          bgcolor: "#fff",
          opacity: pulse,
        }}
      />
      <Typography
        component="span"
        sx={{
          color: "#fff",
          fontSize: 11,
          fontWeight: 800,
          letterSpacing: 1.4,
          lineHeight: 1,
        }}
      >
        {mode}
      </Typography>
    </Box>
  );
};
