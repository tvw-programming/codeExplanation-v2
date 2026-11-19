"""Per-stack brand tokens for Remotion / canvas / Mermaid.

Hex values match the locked multi-stack plan §3. Renderers resolve
theme from `stack` — do not hardcode stack colors in compositions.
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
    "go": {
        "stack": "go",
        "primary": "#00ADD8",
        "secondary": "#00C853",
        "onDark": "#00E5FF",
        "logoAssetId": "go-fiber-logo-ondark",
        "logoPath": "visuals/logos/go.svg",
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
    "express": {
        "stack": "express",
        "primary": "#2C2C2C",
        "secondary": "#FFFFFF",
        "onDark": "#FFFFFF",
        "logoAssetId": "express-logo-ondark",
        "logoPath": "visuals/logos/express.svg",
    },
}

# Shared chrome (dark video plane).
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
