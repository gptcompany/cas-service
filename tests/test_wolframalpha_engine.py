"""Tests for WolframAlphaEngine (Slice D) — template compute, error handling, /engines integration."""

from __future__ import annotations

import json
import urllib.error
from http.server import HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from cas_service.engines.base import Capability, ComputeRequest
from cas_service.engines.wolframalpha_engine import WolframAlphaEngine


# ---------------------------------------------------------------------------
# Unit tests — WolframAlphaEngine directly
# ---------------------------------------------------------------------------


class TestWACapabilities:

    def test_capabilities(self):
        engine = WolframAlphaEngine(app_id="test")
        assert Capability.COMPUTE in engine.capabilities
        assert Capability.REMOTE in engine.capabilities

    def test_validate_not_supported(self):
        engine = WolframAlphaEngine(app_id="test")
        result = engine.validate("x^2")
        assert result.success is False
        assert "not part of the validation consensus" in (result.error or "")

    def test_version(self):
        engine = WolframAlphaEngine(app_id="test")
        assert engine.get_version() == "v2-api"

    def test_available_templates(self):
        templates = WolframAlphaEngine.available_templates()
        assert "evaluate" in templates
        assert "solve" in templates
        assert "simplify" in templates


class TestWAAvailability:

    def test_available_with_appid(self):
        engine = WolframAlphaEngine(app_id="FAKE-ID")
        assert engine.is_available() is True
        assert engine.availability_reason is None

    def test_unavailable_without_appid(self):
        engine = WolframAlphaEngine(app_id="")
        assert engine.is_available() is False
        assert engine.availability_reason == "missing CAS_WOLFRAMALPHA_APPID"

    def test_compute_when_unavailable(self):
        engine = WolframAlphaEngine(app_id="")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "2+2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_UNAVAILABLE"


class TestWATemplateErrors:

    def test_unknown_template(self):
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="nonexistent", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "UNKNOWN_TEMPLATE"

    def test_missing_input(self):
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"


class TestWAAPICall:

    def _mock_response(self, data: dict):
        """Create a mock urllib response."""
        mock = MagicMock()
        mock.read.return_value = json.dumps(data).encode()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_successful_evaluate(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({
            "queryresult": {
                "success": True,
                "pods": [
                    {"id": "Input", "subpods": [{"plaintext": "2 + 2"}]},
                    {"id": "Result", "subpods": [{"plaintext": "4"}]},
                ],
            },
        })
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "2+2"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "4"}
        assert result.stdout == "4"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_solve_template(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({
            "queryresult": {
                "success": True,
                "pods": [
                    {"id": "Input", "subpods": [{"plaintext": "solve x^2 = 4"}]},
                    {"id": "Solution", "subpods": [{"plaintext": "x = -2 or x = 2"}]},
                ],
            },
        })
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="solve", inputs={"equation": "x^2 = 4"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert "x = " in result.result["value"]

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_query_failed(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({
            "queryresult": {"success": False, "tips": {"text": "Check input"}},
        })
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "asdfgh"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "QUERY_FAILED"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_no_result_pod(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response({
            "queryresult": {
                "success": True,
                "pods": [
                    {"id": "Input", "subpods": [{"plaintext": "hello"}]},
                ],
            },
        })
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "hello"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "NO_RESULT"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_http_403_auth_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=403, msg="Forbidden", hdrs={}, fp=None,
        )
        engine = WolframAlphaEngine(app_id="BAD-KEY")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "2+2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "AUTH_ERROR"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "2+2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "NETWORK_ERROR"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("timed out")
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "2+2"},
            timeout_s=3,
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "TIMEOUT"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_fallback_to_non_input_pod(self, mock_urlopen):
        """When no Result/Solution pod, use first non-Input pod."""
        mock_urlopen.return_value = self._mock_response({
            "queryresult": {
                "success": True,
                "pods": [
                    {"id": "Input", "subpods": [{"plaintext": "pi"}]},
                    {"id": "DecimalApproximation", "subpods": [
                        {"plaintext": "3.14159265358979..."},
                    ]},
                ],
            },
        })
        engine = WolframAlphaEngine(app_id="FAKE")
        req = ComputeRequest(
            engine="wolframalpha", task_type="template",
            template="evaluate", inputs={"expression": "pi"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert "3.14159" in result.result["value"]


# ---------------------------------------------------------------------------
# Integration tests — via HTTP server
# ---------------------------------------------------------------------------


@pytest.fixture()
def cas_server_with_wa():
    """Start CAS server with WolframAlpha engine (no real API key)."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    cas_main.ENGINES.clear()

    # One with key, one without
    wa_with_key = WolframAlphaEngine(app_id="FAKE-KEY")
    cas_main.ENGINES["wolframalpha"] = wa_with_key

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)


@pytest.fixture()
def cas_server_wa_unavailable():
    """Start CAS server with WolframAlpha engine without API key."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    cas_main.ENGINES.clear()

    wa_no_key = WolframAlphaEngine(app_id="")
    cas_main.ENGINES["wolframalpha"] = wa_no_key

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)


def _get(addr, path):
    import http.client
    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data


def _post(addr, path, body):
    import http.client
    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    conn.request(
        "POST", path,
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data


class TestWAHTTPIntegration:

    def test_engines_shows_wa_available(self, cas_server_with_wa):
        status, data = _get(cas_server_with_wa, "/engines")
        assert status == 200
        wa = next(e for e in data["engines"] if e["name"] == "wolframalpha")
        assert wa["available"] is True
        assert "compute" in wa["capabilities"]
        assert "remote" in wa["capabilities"]
        assert "availability_reason" not in wa

    def test_engines_shows_wa_unavailable_with_reason(self, cas_server_wa_unavailable):
        status, data = _get(cas_server_wa_unavailable, "/engines")
        assert status == 200
        wa = next(e for e in data["engines"] if e["name"] == "wolframalpha")
        assert wa["available"] is False
        assert wa["availability_reason"] == "missing CAS_WOLFRAMALPHA_APPID"

    def test_compute_wa_unavailable_returns_503(self, cas_server_wa_unavailable):
        status, data = _post(cas_server_wa_unavailable, "/compute", {
            "engine": "wolframalpha",
            "task_type": "template",
            "template": "evaluate",
            "inputs": {"expression": "2+2"},
        })
        assert status == 503
        assert data["code"] == "ENGINE_UNAVAILABLE"

    @patch("cas_service.engines.wolframalpha_engine.urllib.request.urlopen")
    def test_compute_wa_via_http(self, mock_urlopen, cas_server_with_wa):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "queryresult": {
                "success": True,
                "pods": [
                    {"id": "Input", "subpods": [{"plaintext": "2 + 2"}]},
                    {"id": "Result", "subpods": [{"plaintext": "4"}]},
                ],
            },
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        status, data = _post(cas_server_with_wa, "/compute", {
            "engine": "wolframalpha",
            "task_type": "template",
            "template": "evaluate",
            "inputs": {"expression": "2+2"},
        })
        assert status == 200
        assert data["success"] is True
        assert data["result"]["value"] == "4"
