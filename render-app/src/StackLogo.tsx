import { Img, staticFile } from "remotion";
import Box from "@mui/material/Box";
import {
  LOGO_HEIGHT,
  LOGO_INSET,
  LOGO_OPACITY,
  type VisualTheme,
} from "./visualTheme";

/** Top-right technology mark. pointer-events none so canvas clicks pass through. */
export const StackLogo: React.FC<{
  theme: VisualTheme;
  height?: number;
  inset?: number;
}> = ({ theme, height = LOGO_HEIGHT, inset = LOGO_INSET }) => {
  if (!theme.logoPath) {
    return null;
  }
  // On dark video, tint the pill with onDark so Express white / JS yellow read.
  const pill = `${theme.onDark || theme.primary}40`;
  return (
    <Box
      sx={{
        position: "absolute",
        top: inset,
        right: inset,
        zIndex: 7,
        pointerEvents: "none",
        opacity: LOGO_OPACITY,
        display: "flex",
        alignItems: "center",
        gap: "8px",
        bgcolor: pill,
        borderRadius: "6px",
        px: "8px",
        py: "4px",
      }}
    >
      <Img
        src={staticFile(theme.logoPath)}
        style={{ height, width: "auto", display: "block" }}
      />
    </Box>
  );
};
