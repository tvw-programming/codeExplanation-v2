import { createTheme } from "@mui/material/styles";

/**
 * Mirrors render-app/shared/theme.ts.
 *
 * It is copied rather than imported because this is a separate npm
 * package with its own node_modules — importing across would pull a
 * second MUI/React into the bundle. Keep the two in step: the viewer
 * sits next to the videos that theme renders, and a drift shows.
 */
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

/** Fallback brand colour for a stack whose bundles carry no theme. */
export const NEUTRAL_STACK_COLOR = "#9aa3b5";
