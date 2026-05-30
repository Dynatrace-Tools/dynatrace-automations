from unittest import mock

from dynatrace_extension_alert_config.config import env_id_to_url


class TestEnvIdToUrl:
    def test_bare_id(self):
        assert env_id_to_url("abc12345") == "https://abc12345.live.dynatrace.com"

    def test_strips_trailing_slash(self):
        assert env_id_to_url("abc12345/") == "https://abc12345.live.dynatrace.com"

    def test_strips_whitespace(self):
        assert env_id_to_url("  abc12345  ") == "https://abc12345.live.dynatrace.com"

    def test_full_url_returned_unchanged(self):
        url = "https://abc12345.live.dynatrace.com"
        assert env_id_to_url(url) == url

    def test_full_url_with_trailing_slash(self):
        assert env_id_to_url("https://abc12345.live.dynatrace.com/") == "https://abc12345.live.dynatrace.com"

    def test_http_url_returned_unchanged(self):
        url = "http://on-prem.example.com"
        assert env_id_to_url(url) == url


class TestEnvIdOverride:
    def test_env_id_overrides_stored_url(self, tmp_path):
        config_dir = tmp_path / ".dynatrace" / "extensions"
        creds_file = config_dir / "OAuth.json"

        with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
             mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", creds_file):
            from dynatrace_extension_alert_config.config import (
                get_or_prompt_credentials,
                save_credentials,
            )

            stored = {
                "clientId": "dt0s02.TEST",
                "clientSecret": "secret",
                "resource": "urn:dtaccount:12345678-1234-1234-1234-123456789012",
                "environmentUrl": "https://old-env.live.dynatrace.com",
            }
            save_credentials(stored)

            creds = get_or_prompt_credentials(env_id="newenv99")

        assert creds["environmentUrl"] == "https://newenv99.live.dynatrace.com"
        # Other fields are untouched
        assert creds["clientId"] == "dt0s02.TEST"

    def test_no_env_id_keeps_stored_url(self, tmp_path):
        config_dir = tmp_path / ".dynatrace" / "extensions"
        creds_file = config_dir / "OAuth.json"

        with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
             mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", creds_file):
            from dynatrace_extension_alert_config.config import (
                get_or_prompt_credentials,
                save_credentials,
            )

            stored = {
                "clientId": "dt0s02.TEST",
                "clientSecret": "secret",
                "resource": "urn:dtaccount:12345678-1234-1234-1234-123456789012",
                "environmentUrl": "https://original.live.dynatrace.com",
            }
            save_credentials(stored)

            creds = get_or_prompt_credentials()

        assert creds["environmentUrl"] == "https://original.live.dynatrace.com"
