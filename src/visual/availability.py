"""visualAvailability envelope — honesty gates for the three visual capabilities."""

from __future__ import annotations

Availability = str  # "available" | "partial" | "unavailable"

CAPABILITIES = ("componentTree", "lifecycleFlow", "interactiveBreakdown")


def empty_availability(reason: str) -> dict:
    """All three keys unavailable with the same reason (placeholder / empty-valid)."""
    return {
        "componentTree": "unavailable",
        "lifecycleFlow": "unavailable",
        "interactiveBreakdown": "unavailable",
        "reasons": {cap: reason for cap in CAPABILITIES},
    }


def set_capability(
    envelope: dict,
    capability: str,
    status: Availability,
    reason: str | None = None,
) -> dict:
    envelope = dict(envelope)
    reasons = dict(envelope.get("reasons") or {})
    envelope[capability] = status
    if reason:
        reasons[capability] = reason
    elif capability in reasons and status == "available":
        reasons.pop(capability, None)
    envelope["reasons"] = reasons
    return envelope


def is_present(status: str | None) -> bool:
    return status in ("available", "partial")
