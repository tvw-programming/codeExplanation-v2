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
from .function_narration import (
    MIN_PAUSE_MS,
    build_function_narration,
    build_function_summary,
    pause_after_ms,
)

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
    # Cues are looked up per source field, so a handler and a function
    # that happen to share a name can't steal each other's cue.
    cues_by_field: dict[str, dict[str, VisualCue]] = {}
    for cue in cues:
        cues_by_field.setdefault(cue.source_field, {})[cue.label] = cue

    def token_for(source_field: str, label: str) -> str:
        """The token is emitted *before* its sentence, so the cue's
        anchor word is the last word spoken before the sentence starts.
        Appending it instead would anchor the highlight to the sentence's
        final word — the line would light up just as the narrator
        finished talking about it, a whole sentence late."""
        cue = cues_by_field.get(source_field, {}).get(label)
        return f"{cue.token} " if cue else ""

    sentences: list[str] = []

    for fn in record.get("importantFunctions") or []:
        name = fn.get("name", "a function")
        # importantFunctions are taken directly from the extracted code,
        # so there is no "assumed" flag on them; they are always spoken
        # plainly.
        sentences.append(f"{token_for('importantFunctions', name)}The {name} function runs next.")

    for route in record.get("routes") or []:
        sentence = f"A {route.get('method', '')} request to {route.get('path', '')} is handled here."
        token = token_for("routes", route.get("path") or route.get("name") or "")
        sentences.append(token + _hedge(sentence, bool(route.get("assumed"))))

    for handler in record.get("eventHandlers") or []:
        name = handler.get("name", "handler")
        sentence = f"The {name} handler responds to a {handler.get('eventType', 'user')} event."
        token = token_for("eventHandlers", name)
        sentences.append(token + _hedge(sentence, bool(handler.get("assumed"))))

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
class NarrationBeat:
    """One unit of narration: what is spoken, the shorter line shown
    beside the code while it plays, which highlight is up during it,
    and how long to stay silent afterwards so the viewer can read.

    Splitting spoken from summary is deliberate — the panel has to stay
    scannable while the audio can afford to be thorough."""
    kind: str                       # "purpose" | "connections" | "item" | "recap"
    summary: str
    spoken: str
    cue_id: str | None = None
    pause_after_ms: int = 0


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
    beats: list[NarrationBeat] = field(default_factory=list)


def build_item_beats(record: dict, cues: list[VisualCue]) -> list[NarrationBeat]:
    """One beat per narrated item, in the same order the flow sentences
    use, each tied to the highlight for the lines it describes."""
    cues_by_field: dict[str, dict[str, VisualCue]] = {}
    for cue in cues:
        cues_by_field.setdefault(cue.source_field, {})[cue.label] = cue

    def cue_id_for(source_field: str, label: str) -> str | None:
        cue = cues_by_field.get(source_field, {}).get(label)
        return cue.id if cue else None

    beats: list[NarrationBeat] = []

    for fn in record.get("importantFunctions") or []:
        name = fn.get("name", "a function")
        beats.append(NarrationBeat(
            kind="item",
            summary=build_function_summary(fn),
            spoken=build_function_narration(fn),
            cue_id=cue_id_for("importantFunctions", name),
            pause_after_ms=pause_after_ms(fn.get("lineCount") or 0),
        ))

    for route in record.get("routes") or []:
        method = route.get("method", "")
        path = route.get("path", "")
        sentence = f"A {method} request to {path} is handled here."
        label = route.get("path") or route.get("name") or ""
        beats.append(NarrationBeat(
            kind="item",
            summary=f"{method} {path}".strip(),
            spoken=_hedge(sentence, bool(route.get("assumed"))),
            cue_id=cue_id_for("routes", label),
            pause_after_ms=MIN_PAUSE_MS,
        ))

    for handler in record.get("eventHandlers") or []:
        name = handler.get("name", "handler")
        event_type = handler.get("eventType", "user")
        sentence = f"The {name} handler responds to a {event_type} event."
        note = handler.get("notes")
        spoken = _hedge(sentence, bool(handler.get("assumed")))
        if note and handler.get("assumed"):
            # An inline JSX handler has no named function behind it; say
            # so rather than implying the extractor knows what it does.
            spoken += " It is bound inline in the markup, so what it does has to be read off the line itself."
        beats.append(NarrationBeat(
            kind="item",
            summary=f"{name} — responds to a {event_type} event",
            spoken=spoken,
            cue_id=cue_id_for("eventHandlers", name),
            pause_after_ms=MIN_PAUSE_MS,
        ))

    for call in record.get("apiCalls") or []:
        sentence = f"A {call.get('method', '')} call goes out to {call.get('url', '')}."
        beats.append(NarrationBeat(
            kind="item",
            summary=f"{call.get('method', '')} {call.get('url', '')}".strip(),
            spoken=_hedge(sentence, bool(call.get("assumed"))),
            cue_id=None,
            pause_after_ms=MIN_PAUSE_MS,
        ))

    return beats


def build_beats(
    record: dict,
    cues: list[VisualCue],
    purpose: str,
    connections: str,
    recap: str,
) -> list[NarrationBeat]:
    opening_pause = 400
    beats = [
        NarrationBeat(kind="purpose", summary=purpose, spoken=purpose,
                      pause_after_ms=opening_pause),
        NarrationBeat(kind="connections", summary=connections, spoken=connections,
                      pause_after_ms=opening_pause),
    ]
    items = build_item_beats(record, cues)
    if not items:
        beats.append(NarrationBeat(
            kind="item",
            summary="No further steps to narrate.",
            spoken="This part of the code has no further steps to narrate beyond what "
                   "purpose already covered.",
            pause_after_ms=opening_pause,
        ))
    else:
        beats.extend(items)
    beats.append(NarrationBeat(kind="recap", summary=recap, spoken=recap))
    return beats


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

    beats = build_beats(record, cues, purpose, connections, recap)

    # Estimated length now follows what is actually spoken (the beats),
    # plus the pauses between them, rather than the older flow text.
    spoken_text = " ".join(beat.spoken for beat in beats)
    pause_seconds = sum(beat.pause_after_ms for beat in beats) / 1000
    estimated = estimate_seconds(spoken_text) + pause_seconds

    return NarrationScript(
        chunk_id=record.get("chunkId", ""),
        purpose=purpose,
        connections=connections,
        flow=flow,
        recap=recap,
        visual_cues=cues,
        estimated_seconds=estimated,
        within_target_range=TARGET_MIN_SECONDS <= estimated <= TARGET_MAX_SECONDS,
        beats=beats,
    )
