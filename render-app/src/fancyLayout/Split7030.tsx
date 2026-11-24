import Box from "@mui/material/Box";
import { CAPTION_ZONE, COMPOSITION_WIDTH, HEADER_HEIGHT, LEFT_PAD, RIGHT_SAFE } from "./zones";
import { split7030Widths } from "./layoutMath";

export type Split7030Props = {
  main: React.ReactNode;
  aside: React.ReactNode;
  mainFraction?: number;
  width?: number;
  headerClearance?: number;
  captionClearance?: number;
  columnGap?: number;
  /** Visible L3 chrome: accent divider + aside panel framing (fancy chunkView only). */
  asideChrome?: boolean;
  asideTitle?: string;
  accentColor?: string;
  style?: React.CSSProperties;
};

/**
 * L3 — 70% main (code/tree) left, 30% animated bullets right.
 */
export const Split7030: React.FC<Split7030Props> = ({
  main,
  aside,
  mainFraction = 0.7,
  width = COMPOSITION_WIDTH,
  headerClearance = HEADER_HEIGHT,
  captionClearance = CAPTION_ZONE,
  columnGap = 20,
  asideChrome = false,
  asideTitle = "Narration beats",
  accentColor = "#60a5fa",
  style,
}) => {
  const innerWidth = width - LEFT_PAD - RIGHT_SAFE;
  const { leftWidth, rightWidth } = split7030Widths(innerWidth, columnGap, mainFraction);
  const dividerWidth = asideChrome ? 3 : 0;

  return (
    <Box
      sx={{
        position: "absolute",
        left: LEFT_PAD,
        right: RIGHT_SAFE,
        top: headerClearance,
        bottom: captionClearance,
        display: "flex",
        flexDirection: "row",
        alignItems: "stretch",
        gap: `${columnGap}px`,
        boxSizing: "border-box",
        ...style,
      }}
    >
      <Box
        sx={{
          width: leftWidth,
          flexShrink: 0,
          minWidth: 0,
          height: "100%",
          overflow: "hidden",
          ...(asideChrome
            ? {
                borderRadius: "8px",
                outline: `1px solid ${accentColor}22`,
                outlineOffset: -1,
              }
            : {}),
        }}
      >
        {main}
      </Box>
      {asideChrome ? (
        <Box
          sx={{
            width: dividerWidth,
            flexShrink: 0,
            alignSelf: "stretch",
            borderRadius: "2px",
            bgcolor: accentColor,
            opacity: 0.55,
            my: 0.5,
          }}
        />
      ) : null}
      <Box
        sx={{
          width: rightWidth,
          flexShrink: 0,
          minWidth: 0,
          height: "100%",
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-start",
          pt: asideChrome ? 1.25 : 1,
          px: asideChrome ? 1.25 : 0,
          boxSizing: "border-box",
          ...(asideChrome
            ? {
                borderRadius: "10px",
                bgcolor: "rgba(15, 20, 28, 0.94)",
                border: `1px solid ${accentColor}40`,
                boxShadow: `inset 0 0 0 1px ${accentColor}18`,
              }
            : {}),
        }}
      >
        {asideChrome ? (
          <Box
            component="span"
            sx={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 1.2,
              textTransform: "uppercase",
              color: accentColor,
              mb: 1.25,
              flexShrink: 0,
            }}
          >
            {asideTitle}
          </Box>
        ) : null}
        {aside}
      </Box>
    </Box>
  );
};