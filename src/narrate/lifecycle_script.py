"""Short developer-vocabulary beats for one lifecycle flow."""

from __future__ import annotations

from src.render.script_text import strip_visual_tokens


def build_lifecycle_beats(flow: dict, stack: str = "react") -> list[dict]:
    """Present-tense handler / setState / api_call narration for one flow."""
    if not flow:
        return []
    title = flow.get("title") or flow.get("trigger") or "handler"
    steps = flow.get("steps") or []
    beats: list[dict] = []

    beats.append({
        "id": f"{flow.get('id', 'flow')}-trigger",
        "summary": title,
        "spoken": f"When {title} runs,",
        "pause_after_ms": 250,
    })

    for step in steps:
        action = step.get("action")
        label = step.get("label") or action
        assumed = bool(step.get("assumed"))
        if action == "event":
            continue  # covered by trigger beat
        if action == "state_update":
            spoken = f"it updates state via {label}."
        elif action == "api_call":
            spoken = f"it calls {label}."
        elif action == "render":
            spoken = "then React re-renders."
        elif action == "navigate":
            spoken = f"it navigates via {label}."
        else:
            spoken = f"it reaches {label}."
        if assumed:
            spoken = "It looks like " + spoken[0].lower() + spoken[1:]
        clean, _ = strip_visual_tokens(spoken)
        beats.append({
            "id": f"{flow.get('id', 'flow')}-step-{step.get('order')}",
            "summary": label,
            "spoken": clean,
            "pause_after_ms": 300,
            "lineRange": step.get("lineRange"),
        })

    return beats


def script_react_lifecycle_flow(flow: dict) -> list[dict]:
    return build_lifecycle_beats(flow, "react")
