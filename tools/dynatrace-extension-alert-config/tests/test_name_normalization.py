from dynatrace_extension_alert_config.extensions import _fuzzy_match, _normalize_name


class TestNormalizeName:
    def test_strips_extension_word(self):
        assert _normalize_name("Meraki Extension") == "meraki"

    def test_lowercase(self):
        assert _normalize_name("MERAKI") == "meraki"

    def test_collapses_spaces(self):
        assert _normalize_name("meraki  extension") == "meraki"


class TestFuzzyMatch:
    def test_exact_tail_match(self):
        candidates = ["com.dynatrace.extension.meraki", "com.dynatrace.extension.aws"]
        assert _fuzzy_match("meraki", candidates) == "com.dynatrace.extension.meraki"

    def test_partial_match(self):
        candidates = ["com.dynatrace.extension.meraki-network"]
        result = _fuzzy_match("meraki", candidates)
        assert result is not None

    def test_no_match_returns_none(self):
        candidates = ["com.dynatrace.extension.aws"]
        assert _fuzzy_match("meraki", candidates) is None

    def test_extension_suffix_stripped(self):
        candidates = ["com.dynatrace.extension.meraki"]
        assert _fuzzy_match("Meraki Extension", candidates) == "com.dynatrace.extension.meraki"
