import { createTheme } from "@mui/material/styles";

// The one MUI theme shared by every component in render-app: the Remotion
// video compositions under ../src (CodeExplainerChunk, Composition) and the
// standalone documentation viewer under ../docs-viewer-src. Both import
// this same module (they share render-app's node_modules, so there's a
// single MUI/React version across the whole project) so the dark palette,
// typography, and shape tokens never drift apart between the two.
export const theme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: "#0f1115",
      paper: "#161923",
    },
    primary: {
      main: "#6ea8fe",
    },
    divider: "#262b3a",
    text: {
      primary: "#e4e7ee",
      secondary: "#9aa3b5",
    },
  },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
  },
  shape: {
    borderRadius: 8,
  },
});
