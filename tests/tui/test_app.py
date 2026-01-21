from sec_nlp.tui.app import SegmentMatcher


def test_segment_matcher_detects_matches() -> None:
    matcher = SegmentMatcher((("alpha",), ("beta",)))
    assert matcher.match("alpha done") == 0
    assert matcher.match("beta done") == 1
    assert matcher.match("gamma") is None
