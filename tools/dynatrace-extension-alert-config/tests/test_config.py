import json
from unittest import mock


def test_save_and_load_credentials(tmp_path):
    config_dir = tmp_path / ".dynatrace" / "extensions"

    with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
         mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", config_dir / "OAuth.json"):
        from dynatrace_extension_alert_config.config import load_credentials, save_credentials

        creds = {
            "clientId": "dt0s02.TEST",
            "clientSecret": "supersecret",
            "resource": "urn:dtaccount:12345678-1234-1234-1234-123456789012",
            "environmentUrl": "https://abc12345.live.dynatrace.com",
        }
        save_credentials(creds)
        loaded = load_credentials()

    assert loaded is not None
    assert loaded["clientId"] == "dt0s02.TEST"
    assert loaded["environmentUrl"] == "https://abc12345.live.dynatrace.com"


def test_save_credentials_file_permissions(tmp_path):
    config_dir = tmp_path / ".dynatrace" / "extensions"
    creds_file = config_dir / "OAuth.json"

    with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
         mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", creds_file):
        from dynatrace_extension_alert_config.config import save_credentials

        creds = {
            "clientId": "dt0s02.TEST",
            "clientSecret": "supersecret",
            "resource": "urn:dtaccount:12345678-1234-1234-1234-123456789012",
            "environmentUrl": "https://abc12345.live.dynatrace.com",
        }
        save_credentials(creds)

    file_stat = creds_file.stat()
    # Only owner should be able to read/write (0o600)
    assert file_stat.st_mode & 0o777 == 0o600


def test_load_credentials_missing_fields(tmp_path):
    config_dir = tmp_path / ".dynatrace" / "extensions"
    config_dir.mkdir(parents=True)
    creds_file = config_dir / "OAuth.json"
    creds_file.write_text(json.dumps({"clientId": "only-this"}))

    with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
         mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", creds_file):
        from dynatrace_extension_alert_config.config import load_credentials
        assert load_credentials() is None


def test_load_credentials_invalid_json(tmp_path):
    config_dir = tmp_path / ".dynatrace" / "extensions"
    config_dir.mkdir(parents=True)
    creds_file = config_dir / "OAuth.json"
    creds_file.write_text("not-json{{")

    with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
         mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", creds_file):
        from dynatrace_extension_alert_config.config import load_credentials
        assert load_credentials() is None


def test_load_credentials_nonexistent(tmp_path):
    config_dir = tmp_path / ".dynatrace" / "extensions"
    creds_file = config_dir / "OAuth.json"

    with mock.patch("dynatrace_extension_alert_config.config.CONFIG_DIR", config_dir), \
         mock.patch("dynatrace_extension_alert_config.config.CREDS_FILE", creds_file):
        from dynatrace_extension_alert_config.config import load_credentials
        assert load_credentials() is None
