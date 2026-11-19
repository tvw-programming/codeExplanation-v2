from src.extract.common import confidence_from_flags, confidence_level


def test_finding_nothing_scores_low_not_high():
    """An extractor that came away empty is the least confident it can
    be. Returning the 0.95 base meant an Angular component — whose
    class methods and @Input()s match no TypeScript pattern — was
    reported at high confidence with every list empty, hiding the fact
    that the stack was not really supported."""
    empty = confidence_from_flags(total_claims=0, assumed_claims=0)
    assert empty < 0.6
    assert confidence_level(empty) == "low"


def test_confidence_still_falls_as_claims_are_marked_assumed():
    assert confidence_from_flags(10, 0) == 0.95
    assert confidence_from_flags(10, 5) < confidence_from_flags(10, 1)
    assert confidence_from_flags(10, 10) >= 0.05


def test_confidence_never_goes_below_the_floor():
    assert confidence_from_flags(1, 1) >= 0.05
