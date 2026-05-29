from unittest import mock

from dynatrace_extension_alert_config.client import DynatraceApiError, _extract_error


class _FakeResp:
    def __init__(self, status, json_body=None, text=""):
        self.status_code = status
        self._json = json_body
        self.text = text
        self.ok = 200 <= status < 300

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def test_extract_403_required_scope_list():
    resp = _FakeResp(
        403,
        {"error": {"code": 403, "message": "Token is missing required scope. Use one of: [extensions.read, extensions.write]"}},
    )
    err = _extract_error(resp)
    assert isinstance(err, DynatraceApiError)
    assert err.status == 403
    assert "extensions.read" in err.required_scopes
    assert "extensions.write" in err.required_scopes


def test_extract_403_single_scope_no_brackets():
    resp = _FakeResp(
        403,
        {"error": {"message": "Token is missing required scope. Use one of: extensions.read"}},
    )
    err = _extract_error(resp)
    assert err.required_scopes == ["extensions.read"]


def test_extract_non_scope_error():
    resp = _FakeResp(400, {"error": {"message": "Constraint violation on value"}})
    err = _extract_error(resp)
    assert err.status == 400
    assert err.required_scopes == []
    assert "Constraint violation" in err.message


def test_extract_plain_text_body():
    resp = _FakeResp(500, json_body=None, text="Internal Server Error")
    err = _extract_error(resp)
    assert err.status == 500
    assert err.message == "Internal Server Error"
    assert err.required_scopes == []
