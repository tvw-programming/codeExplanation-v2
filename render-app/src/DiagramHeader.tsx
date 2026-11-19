import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { StackLogo } from "./StackLogo";
import {
  CEV_FG_MUTED,
  CEV_FG_PRIMARY,
  type VisualTheme,
} from "./visualTheme";
import { HEADER_HEIGHT } from "./treeLayout";

/** Shorten long paths the way FileCard does. */
export function shortFilePath(path: string | null | undefined): string {
  if (!path) return "";
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 3) return path;
  return ".../" + parts.slice(-3).join("/");
}

/**
 * MUI AppBar-style chrome for every FullVideo segment (FileCard, tree,
 * lifecycle, ChunkView, breakdown). Brand-tinted bar + file path;
 * logo stays top-right inside the bar.
 */
export const DiagramHeader: React.FC<{
  theme: VisualTheme;
  filePath?: string | null;
  eyebrow?: string;
  titleFallback?: string;
}> = ({ theme, filePath, eyebrow, titleFallback }) => {
  const pathLabel = shortFilePath(filePath) || titleFallback || theme.stack;
  const barTint = `${theme.onDark || theme.primary}33`;
  const underline = theme.onDark || theme.primary;

  return (
    <Box
      sx={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: HEADER_HEIGHT,
        zIndex: 6,
        display: "flex",
        alignItems: "center",
        px: "20px",
        pr: "120px",
        bgcolor: barTint,
        borderBottom: `2px solid ${underline}`,
        boxSizing: "border-box",
      }}
    >
      <Box sx={{ minWidth: 0, flex: 1 }}>
        {eyebrow ? (
          <Typography
            sx={{
              color: CEV_FG_MUTED,
              fontSize: 11,
              letterSpacing: 1.2,
              lineHeight: 1.1,
              textTransform: "uppercase",
            }}
          >
            {eyebrow}
          </Typography>
        ) : null}
        <Typography
          sx={{
            color: CEV_FG_PRIMARY,
            fontSize: 15,
            fontWeight: 600,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            lineHeight: 1.3,
          }}
        >
          {pathLabel}
        </Typography>
      </Box>
      <StackLogo theme={theme} inset={10} height={24} />
    </Box>
  );
};
