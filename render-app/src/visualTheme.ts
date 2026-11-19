/** Per-stack brand tokens — keep in sync with src/visual/theme.py */

export type VisualTheme = {
  stack: string;
  primary: string;
  secondary: string;
  onDark: string;
  logoAssetId: string;
  logoPath?: string | null;
};

export const CEV_BG_VIDEO = "#0F1419";
export const CEV_FG_PRIMARY = "#F3F4F6";
export const CEV_FG_MUTED = "#9CA3AF";
export const CEV_SECURITY = "#F59E0B";

export const VISUAL_THEME_BY_STACK: Record<string, VisualTheme> = {
  react: {
    stack: "react",
    primary: "#61DAFB",
    secondary: "#087EA4",
    onDark: "#61DAFB",
    logoAssetId: "react-logo-ondark",
    logoPath: "visuals/logos/react.svg",
  },
  go: {
    stack: "go",
    primary: "#00ADD8",
    secondary: "#00C853",
    onDark: "#00E5FF",
    logoAssetId: "go-fiber-logo-ondark",
    logoPath: "visuals/logos/go-fiber.svg",
  },
  gofiber: {
    stack: "go",
    primary: "#00ADD8",
    secondary: "#00C853",
    onDark: "#00E5FF",
    logoAssetId: "go-fiber-logo-ondark",
    logoPath: "visuals/logos/go-fiber.svg",
  },
  go_fiber: {
    stack: "go",
    primary: "#00ADD8",
    secondary: "#00C853",
    onDark: "#00E5FF",
    logoAssetId: "go-fiber-logo-ondark",
    logoPath: "visuals/logos/go-fiber.svg",
  },
};

export function themeForStack(stack: string | undefined | null): VisualTheme {
  const key = (stack || "").replace(/-/g, "_");
  if (VISUAL_THEME_BY_STACK[key]) {
    return VISUAL_THEME_BY_STACK[key];
  }
  return {
    stack: stack || "unknown",
    primary: "#9CA3AF",
    secondary: "#6B7280",
    onDark: "#D1D5DB",
    logoAssetId: "unknown",
    logoPath: null,
  };
}

/** Logo safe zone: 24px inset, 28px logo height (Remotion 1280×720). */
export const LOGO_INSET = 24;
export const LOGO_HEIGHT = 28;
export const LOGO_OPACITY = 0.88;
