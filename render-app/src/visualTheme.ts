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
export const CEV_FG_ON_LIGHT = "#111827";

/** Locked multi-stack plan §3.2 tokens (canonical stack keys). */
export const VISUAL_THEME_BY_STACK: Record<string, VisualTheme> = {
  react: {
    stack: "react",
    primary: "#61DAFB",
    secondary: "#087EA4",
    onDark: "#61DAFB",
    logoAssetId: "react-logo-ondark",
    logoPath: "visuals/logos/react.svg",
  },
  angular: {
    stack: "angular",
    primary: "#DD0031",
    secondary: "#C3002F",
    onDark: "#FF4D6A",
    logoAssetId: "angular-logo-ondark",
    logoPath: "visuals/logos/angular.svg",
  },
  vue: {
    stack: "vue",
    primary: "#42B883",
    secondary: "#35495E",
    onDark: "#42B883",
    logoAssetId: "vue-logo-ondark",
    logoPath: "visuals/logos/vue.svg",
  },
  solid: {
    stack: "solid",
    primary: "#2C4F7C",
    secondary: "#0CDC73",
    onDark: "#0CDC73",
    logoAssetId: "solid-logo-ondark",
    logoPath: "visuals/logos/solid.svg",
  },
  qwik: {
    stack: "qwik",
    primary: "#009DFD",
    secondary: "#AC7EF4",
    onDark: "#009DFD",
    logoAssetId: "qwik-logo-ondark",
    logoPath: "visuals/logos/qwik.svg",
  },
  javascript: {
    stack: "javascript",
    primary: "#F7DF1E",
    secondary: "#323330",
    onDark: "#F7DF1E",
    logoAssetId: "javascript-logo-ondark",
    logoPath: "visuals/logos/javascript.svg",
  },
  python: {
    stack: "python",
    primary: "#3776AB",
    secondary: "#FFD43B",
    onDark: "#4B8BBE",
    logoAssetId: "python-logo-ondark",
    logoPath: "visuals/logos/python.svg",
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
  spring_boot: {
    stack: "spring_boot",
    primary: "#6DB33F",
    secondary: "#6DB33F",
    onDark: "#8BC34A",
    logoAssetId: "spring-logo-ondark",
    logoPath: "visuals/logos/spring.svg",
  },
  /** Alias used by some detect paths. */
  java: {
    stack: "java",
    primary: "#6DB33F",
    secondary: "#6DB33F",
    onDark: "#8BC34A",
    logoAssetId: "spring-logo-ondark",
    logoPath: "visuals/logos/spring.svg",
  },
  spring: {
    stack: "spring_boot",
    primary: "#6DB33F",
    secondary: "#6DB33F",
    onDark: "#8BC34A",
    logoAssetId: "spring-logo-ondark",
    logoPath: "visuals/logos/spring.svg",
  },
  express: {
    stack: "express",
    primary: "#2C2C2C",
    secondary: "#FFFFFF",
    onDark: "#FFFFFF",
    logoAssetId: "express-logo-ondark",
    logoPath: "visuals/logos/express.svg",
  },
  rust: {
    stack: "rust",
    primary: "#D34516",
    secondary: "#1E2650",
    onDark: "#FF6B35",
    logoAssetId: "rust-logo-ondark",
    logoPath: "visuals/logos/rust.svg",
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

/** Stroke / edge accent on the dark video plane (plan §3.1). */
export function videoAccent(theme: VisualTheme): string {
  return theme.onDark || theme.primary;
}

/**
 * Label text on dark-video nodes.
 * JS yellow pills use dark secondary text; others use light fg.
 */
export function videoLabelColor(theme: VisualTheme): string {
  if (theme.stack === "javascript") {
    return theme.secondary || CEV_FG_ON_LIGHT;
  }
  return CEV_FG_PRIMARY;
}

/** Logo safe zone: 24px inset, 28px logo height (Remotion 1280×720). */
export const LOGO_INSET = 24;
export const LOGO_HEIGHT = 28;
export const LOGO_OPACITY = 0.88;
