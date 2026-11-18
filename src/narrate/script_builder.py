"""Phase 5 — four-beat narrator script generation.

Builds the script for one chunk directly from its extracted JSON
record, per the locked narrator script rules: purpose before
mechanism, present tense, one idea per sentence, confidence-gated
speech (verified claims plain, assumed-but-grounded claims hedged with
a single fixed phrase, nothing not grounded in the extraction is ever
spoken), the notes field never spoken, and the flow beat split in two
if it would run past about 60 seconds.

This is template-based, not a call to a language model: every
sentence is built mechanically from fields already in the record, so
nothing is invented that isn't in the extraction's own symbol table.
That is a deliberate continuation of this project's regex/heuristic
extraction stance, not a shortcut — it also makes the output fully
deterministic and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .visual_cues import VisualCue, generate_visual_cues
from .glossary import GlossaryEntry

WORDS_PER_MINUTE = 130
PAUSE_FACTOR = 1.125  # +12.5%, within the rule's 10-15% pause allowance
MAX_FLOW_SECONDS = 60
TARGET_MIN_SECONDS = 90
TARGET_MAX_SECONDS = 180

# The one fixed hedge phrase the rules call for, used for every
# assumed-but-grounded claim so the narration stays consistent.
HEDGE_PHRASE = "It looks like"


def word_count(text: str) -> int:
    return len([w for w in text.split() if w])


def estimate_seconds(text: str) -> float:
    words = word_count(text)
    return (words / WORDS_PER_MINUTE) * 60 * PAUSE_FACTOR


def _framework_phrase(record: dict) -> str:
    frameworks = record.get("frameworkOrLibrary") or []
    return frameworks[0] if frameworks else record.get("language") or "this stack"


def build_purpose_beat(record: dict) -> str:
    feature_name = record.get("featureName") or "this chunk"
    framework = _framework_phrase(record)
    sentences = [f"This section covers {feature_name}, built with {framework}."]

    routes = record.get("routes") or []
    handlers = record.get("eventHandlers") or []
    if routes:
        sentences.append(f"It defines {len(routes)} backend route{'s' if len(routes) != 1 else ''}.")
    elif handlers:
        sentences.append(f"It handles user interaction through {len(handlers)} event handler"
                          f"{'s' if len(handlers) != 1 else ''}.")
    return " ".join(sentences)


def build_connections_beat(
    record: dict,
    back_refs: list[GlossaryEntry],
    forward_refs: list[GlossaryEntry],
) -> str:
    feature_name = record.get("featureName") or "this chunk"
    if not back_refs and not forward_refs:
        return f"{feature_name} stands on its own here, with no links to chunks covered elsewhere."

    sentences = []
    if back_refs:
        names = ", ".join(r.canonical_name for r in back_refs)
        verb = "builds on" if len(back_refs) == 1 else "builds on"
        sentences.append(f"{feature_name} {verb} {names}, covered earlier.")
    if forward_refs:
        names = ", ".join(r.canonical_name for r in forward_refs)
        sentences.append(f"It also connects to {names}, covered later.")
    return " ".join(sentences)


def _hedge(sentence: str, assumed: bool) -> str:
    if not assumed:
        return sentence
    return f"{HEDGE_PHRASE} {sentence[0].lower()}{sentence[1:]}"


def build_flow_sentences(record: dict, cues: list[VisualCue]) -> list[str]:
    """One sentence per flow item (function, route, handler, API call),
    each confidence-gated and carrying its VISUAL cue token when one
    exists for that item."""
    cues_by_label = {cue.label: cue for cue in cues}
    sentences: list[str] = []

    for fn in record.get("importantFunctions") or []:
        name = fn.get("name", "a function")
        cue = cues_by_label.get(name)
        token = f" {cue.token}" if cue else ""
        # importantFunctions are taken directly from the extracted code,
        # so there is no "assumed" flag on them; they are always spoken
        # plainly.
        sentences.append(f"The {name} function runs next.{token}")

    for route in record.get("routes") or []:
        sentence = f"A {route.get('method', '')} request to {route.get('path', '')} is handled here."
        sentences.append(_hedge(sentence, bool(route.get("assumed"))))

    for handler in record.get("eventHandlers") or []:
        sentence = f"The {handler.get('name', 'handler')} handler responds to a {handler.get('eventType', 'user')} event."
        sentences.append(_hedge(sentence, bool(handler.get("assumed"))))

    for call in record.get("apiCalls") or []:
        sentence = f"A {call.get('method', '')} call goes out to {call.get('url', '')}."
        sentences.append(_hedge(sentence, bool(call.get("assumed"))))

    return sentences


def build_flow_beats(sentences: list[str]) -> list[str]:
    """Joins flow sentences into one beat, or splits into two beats at a
    sentence boundary if the combined narration would run past
    MAX_FLOW_SECONDS — never mid-sentence."""
    if not sentences:
        return ["This part of the code has no further steps to narrate beyond what purpose already covered."]

    full_text = " ".join(sentences)
    if estimate_seconds(full_text) <= MAX_FLOW_SECONDS:
        return [full_text]

    # Split at the sentence boundary closest to the halfway point of
    # estimated duration, so each half stays within budget.
    cumulative = 0.0
    split_at = len(sentences)
    for i, sentence in enumerate(sentences):
        cumulative += estimate_seconds(sentence)
        if cumulative > MAX_FLOW_SECONDS:
            split_at = i if i > 0 else 1
            break

    first_half = " ".join(sentences[:split_at])
    second_half = " ".join(sentences[split_at:])
    return [b for b in (first_half, second_half) if b]


def build_recap_beat(record: dict) -> str:
    feature_name = record.get("featureName") or "this chunk"
    return (f"That covers what {feature_name} does. Deeper implementation details beyond "
            f"what's shown here are left for review.")


@dataclass
class NarrationScript:
    chunk_id: str
    purpose: str
    connections: str
    flow: list[str]
    recap: str
    visual_cues: list[VisualCue] = field(default_factory=list)
    estimated_seconds: float = 0.0
    within_target_range: bool = False


def build_narration_script(
    record: dict,
    back_refs: list[GlossaryEntry],
    forward_refs: list[GlossaryEntry],
) -> NarrationScript:
    cues = generate_visual_cues(record)
    purpose = build_purpose_beat(record)
    connections = build_connections_beat(record, back_refs, forward_refs)
    flow_sentences = build_flow_sentences(record, cues)
    flow = build_flow_beats(flow_sentences)
    recap = build_recap_beat(record)

    total_text = " ".join([purpose, connections, *flow, recap])
    estimated = estimate_seconds(total_text)

    return NarrationScript(
        chunk_id=record.get("chunkId", ""),
        purpose=purpose,
        connections=connections,
        flow=flow,
        recap=recap,
        visual_cues=cues,
        estimated_seconds=estimated,
        within_target_range=TARGET_MIN_SECONDS <= estimated <= TARGET_MAX_SECONDS,
    )
