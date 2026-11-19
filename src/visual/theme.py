"""Per-stack brand tokens for Remotion / canvas / Mermaid.

Hex values match the locked multi-stack plan §3.
"""

from __future__ import annotations

VISUAL_THEME_BY_STACK: dict[str, dict] = {
    "react": {
        "stack": "react",
        "primary": "#61DAFB",
        "secondary": "#087EA4",
        "onDark": "#61DAFB",
        "logoAssetId": "react-logo-ondark",
        "logoPath": "visuals/logos/react.svg",
    },
    "angular": {
        "stack": "angular",
        "primary": "#DD0031",
        "secondary": "#C3002F",
        "onDark": "#FF4D6A",
        "logoAssetId": "angular-logo-ondark",
        "logoPath": "visuals/logos/angular.svg",
    },
    "vue": {
        "stack": "vue",
        "primary": "#42B883",
        "secondary": "#35495E",
        "onDark": "#42B883",
        "logoAssetId": "vue-logo-ondark",
        "logoPath": "visuals/logos/vue.svg",
    },
    "solid": {
        "stack": "solid",
        "primary": "#2C4F7C",
        "secondary": "#0CDC73",
        "onDark": "#0CDC73",
        "logoAssetId": "solid-logo-ondark",
        "logoPath": "visuals/logos/solid.svg",
    },
    "qwik": {
        "stack": "qwik",
        "primary": "#009DFD",
        "secondary": "#AC7EF4",
        "onDark": "#009DFD",
        "logoAssetId": "qwik-logo-ondark",
        "logoPath": "visuals/logos/qwik.svg",
    },
    "javascript": {
        "stack": "javascript",
        "primary": "#F7DF1E",
        "secondary": "#323330",
        "onDark": "#F7DF1E",
        "logoAssetId": "javascript-logo-ondark",
        "logoPath": "visuals/logos/javascript.svg",
    },
    "go": {
        "stack": "go",
        "primary": "#00ADD8",
        "secondary": "#00C853",
        "onDark": "#00E5FF",
        "logoAssetId": "go-fiber-logo-ondark",
        "logoPath": "visuals/logos/go-fiber.svg",
    },
    "gofiber": {
        "stack": "go",
        "primary": "#00ADD8",
        "secondary": "#00C853",
        "onDark": "#00E5FF",
        "logoAssetId": "go-fiber-logo-ondark",
        "logoPath": "visuals/logos/go-fiber.svg",
    },
    "go_fiber": {
        "stack": "go",
        "primary": "#00ADD8",
        "secondary": "#00C853",
        "onDark": "#00E5FF",
        "logoAssetId": "go-fiber-logo-ondark",
        "logoPath": "visuals/logos/go-fiber.svg",
    },
    "python": {
        "stack": "python",
        "primary": "#3776AB",
        "secondary": "#FFD43B",
        "onDark": "#4B8BBE",
        "logoAssetId": "python-logo-ondark",
        "logoPath": "visuals/logos/python.svg",
    },
    "spring_boot": {
        "stack": "spring_boot",
        "primary": "#6DB33F",
        "secondary": "#6DB33F",
        "onDark": "#8BC34A",
        "logoAssetId": "spring-logo-ondark",
        "logoPath": "visuals/logos/spring.svg",
    },
    "java": {
        "stack": "java",
        "primary": "#6DB33F",
        "secondary": "#6DB33F",
        "onDark": "#8BC34A",
        "logoAssetId": "spring-logo-ondark",
        "logoPath": "visuals/logos/spring.svg",
    },
    "spring": {
        "stack": "spring_boot",
        "primary": "#6DB33F",
        "secondary": "#6DB33F",
        "onDark": "#8BC34A",
        "logoAssetId": "spring-logo-ondark",
        "logoPath": "visuals/logos/spring.svg",
    },
    "express": {
        "stack": "express",
        "primary": "#2C2C2C",
        "secondary": "#FFFFFF",
        "onDark": "#FFFFFF",
        "logoAssetId": "express-logo-ondark",
        "logoPath": "visuals/logos/express.svg",
    },
    "rust": {
        "stack": "rust",
        "primary": "#D34516",
        "secondary": "#1E2650",
        "onDark": "#FF6B35",
        "logoAssetId": "rust-logo-ondark",
        "logoPath": "visuals/logos/rust.svg",
    },
}

CEV_BG_VIDEO = "#0F1419"
CEV_BG_CANVAS = "#111827"
CEV_FG_PRIMARY = "#F3F4F6"
CEV_FG_MUTED = "#9CA3AF"
CEV_SECURITY = "#F59E0B"
CEV_UNAVAILABLE = "#6B7280"


def theme_for_stack(stack: str | None) -> dict:
    key = (stack or "").replace("-", "_")
    if key in VISUAL_THEME_BY_STACK:
        return dict(VISUAL_THEME_BY_STACK[key])
    return {
        "stack": stack or "unknown",
        "primary": "#9CA3AF",
        "secondary": "#6B7280",
        "onDark": "#D1D5DB",
        "logoAssetId": "unknown",
        "logoPath": None,
    }
