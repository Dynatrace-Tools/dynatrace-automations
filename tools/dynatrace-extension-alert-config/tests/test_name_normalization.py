from dynatrace_extension_alert_config.docs_scraper import slugify
from dynatrace_extension_alert_config.extensions import _normalize_name, _fuzzy_match


class TestSlugify:
    def test_meraki(self):
        assert slugify("meraki") == "meraki"

    def test_meraki_extension_title_case(self):
        assert slugify("Meraki Extension") == "meraki"

    def test_microsoft_365_office_365(self):
        assert slugify("Microsoft 365, Office 365") == "microsoft-365-office-365"

    def test_leading_trailing_spaces(self):
        assert slugify("  meraki  ") == "meraki"

    def test_special_chars_replaced(self):
        assert slugify("my/tool.name") == "my-tool-name"

    def test_no_double_hyphens(self):
        result = slugify("foo   bar")
        assert "--" not in result

    def test_lowercase_output(self):
        assert slugify("MERAKI") == "meraki"


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
