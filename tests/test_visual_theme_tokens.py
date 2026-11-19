"""Brand tokens must match visual-diagrams-multi-stack-plan §3.2."""

from __future__ import annotations

from pathlib import Path

from src.visual.theme import VISUAL_THEME_BY_STACK, theme_for_stack

# Canonical plan §3.2 rows (stack key → primary, secondary, onDark).
PLAN_TOKENS = {
    "react": ("#61DAFB", "#087EA4", "#61DAFB"),
    "angular": ("#DD0031", "#C3002F", "#FF4D6A"),
    "vue": ("#42B883", "#35495E", "#42B883"),
    "solid": ("#2C4F7C", "#0CDC73", "#0CDC73"),
    "qwik": ("#009DFD", "#AC7EF4", "#009DFD"),
    "javascript": ("#F7DF1E", "#323330", "#F7DF1E"),
    "python": ("#3776AB", "#FFD43B", "#4B8BBE"),
    "go": ("#00ADD8", "#00C853", "#00E5FF"),
    "go_fiber": ("#00ADD8", "#00C853", "#00E5FF"),
    "spring_boot": ("#6DB33F", "#6DB33F", "#8BC34A"),
    "express": ("#2C2C2C", "#FFFFFF", "#FFFFFF"),
    "rust": ("#D34516", "#1E2650", "#FF6B35"),
}

LOGO_DIR = Path(__file__).resolve().parents[1] / "render-app" / "public" / "visuals" / "logos"

# TS theme map must list the same hex for these stacks (parity check via file text).
TS_THEME = (
    Path(__file__).resolve().parents[1] / "render-app" / "src" / "visualTheme.ts"
)


def test_plan_tokens_present_for_all_stacks():
    for stack, (primary, secondary, on_dark) in PLAN_TOKENS.items():
        theme = theme_for_stack(stack)
        assert theme["primary"] == primary, stack
        assert theme["secondary"] == secondary, stack
        assert theme["onDark"] == on_dark, stack
        assert theme["logoPath"], stack
        assert theme["logoAssetId"], stack


def test_react_cyan_brand():
    assert theme_for_stack("react")["primary"] == "#61DAFB"
    assert theme_for_stack("react")["onDark"] == "#61DAFB"


def test_express_on_dark_is_white():
    """Charcoal primary is unreadable on #0F1419 — video must use onDark white."""
    t = theme_for_stack("express")
    assert t["primary"] == "#2C2C2C"
    assert t["onDark"] == "#FFFFFF"


def test_logo_files_exist_for_every_theme_path():
    paths = {
        t["logoPath"]
        for t in VISUAL_THEME_BY_STACK.values()
        if t.get("logoPath")
    }
    for rel in paths:
        # logoPath is like visuals/logos/react.svg relative to public/
        name = Path(rel).name
        assert (LOGO_DIR / name).is_file(), rel


def test_ts_theme_file_contains_plan_hex():
    text = TS_THEME.read_text()
    for stack, (primary, secondary, on_dark) in PLAN_TOKENS.items():
        if stack == "go_fiber":
            continue  # alias shares go block
        assert primary in text, f"{stack} primary missing in visualTheme.ts"
        assert on_dark in text, f"{stack} onDark missing in visualTheme.ts"


def test_aliases_resolve():
    assert theme_for_stack("go-fiber")["primary"] == "#00ADD8"
    assert theme_for_stack("gofiber")["onDark"] == "#00E5FF"
    assert theme_for_stack("spring")["primary"] == "#6DB33F"
    assert theme_for_stack("java")["logoAssetId"] == "spring-logo-ondark"
