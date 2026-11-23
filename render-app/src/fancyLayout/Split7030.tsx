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
  style,
}) => {
  const innerWidth = width - LEFT_PAD - RIGHT_SAFE;
  const { leftWidth, rightWidth } = split7030Widths(innerWidth, columnGap, mainFraction);

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
        }}
      >
        {main}
      </Box>
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
          pt: 1,
        }}
      >
        {aside}
      </Box>
    </Box>
  );
};