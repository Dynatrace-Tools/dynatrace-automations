from dynatrace_extension_alert_config.recommendations import (
    format_number,
    recommend_threshold,
)


class TestPercent:
    def test_percent_above(self):
        assert recommend_threshold("Percent", "ABOVE") == 80.0

    def test_percent_below(self):
        assert recommend_threshold("Percent", "BELOW") == 20.0

    def test_percent_case_insensitive(self):
        assert recommend_threshold("percent", "ABOVE") == 80.0
        assert recommend_threshold("PERCENT", "ABOVE") == 80.0

    def test_percent_symbol(self):
        assert recommend_threshold("%", "ABOVE") == 80.0


class TestRatio:
    def test_ratio_above(self):
        assert recommend_threshold("Ratio", "ABOVE") == 0.8

    def test_ratio_below(self):
        assert recommend_threshold("Ratio", "BELOW") == 0.2


class TestUnknown:
    def test_unknown_unit_returns_none(self):
        assert recommend_threshold("MilliSecond", "ABOVE") is None

    def test_empty_unit_returns_none(self):
        assert recommend_threshold("", "ABOVE") is None

    def test_byte_returns_none(self):
        assert recommend_threshold("Byte", "BELOW") is None


class TestFormatNumber:
    def test_integer_no_trailing_zero(self):
        assert format_number(80.0) == "80"

    def test_decimal_preserved(self):
        assert format_number(0.8) == "0.8"
