"""Additional tests for main.py to increase coverage of HTTP handler and engine init."""

from __future__ import annotations

import json
import logging
from http.server import HTTPServer
from threading import Thread
import http.client
import pytest
from unittest.mock import patch, MagicMock

import cas_service.main as cas_main
from cas_service.engines.base import BaseEngine, EngineResult, Capability


# Reuse fixtures or create similar ones
@pytest.fixture(autouse=True)
def restore_main_globals():
    """Restore mutable module globals touched by coverage tests."""
    original_engines = cas_main.ENGINES.copy()
    original_default = cas_main._default_engine
    original_pool = cas_main._validate_pool
    try:
        yield
    finally:
        cas_main.ENGINES.clear()
        cas_main.ENGINES.update(original_engines)
        cas_main._default_engine = original_default
        cas_main._validate_pool = original_pool


@pytest.fixture()
def mock_server():
    """Start a CAS HTTP server with minimal mock engines."""
    original_engines = cas_main.ENGINES.copy()
    original_default = cas_main._default_engine
    cas_main.ENGINES.clear()

    class MockEngine(BaseEngine):
        name = "mock"

        def validate(self, latex):
            return EngineResult(engine="mock", success=True, is_valid=True)

        def is_available(self):
            return True

        def get_version(self):
            return "1.0"

    cas_main.ENGINES["mock"] = MockEngine()
    cas_main._default_engine = "mock"

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)
    cas_main._default_engine = original_default


def test_unknown_get_path(mock_server):
    conn = http.client.HTTPConnection(mock_server[0], mock_server[1])
    conn.request("GET", "/unknown")
    resp = conn.getresponse()
    assert resp.status == 404
    conn.close()


def test_unknown_post_path(mock_server):
    conn = http.client.HTTPConnection(mock_server[0], mock_server[1])
    conn.request("POST", "/unknown", body=b"{}")
    resp = conn.getresponse()
    assert resp.status == 404
    conn.close()


def test_validate_invalid_json(mock_server):
    conn = http.client.HTTPConnection(mock_server[0], mock_server[1])
    conn.request(
        "POST",
        "/validate",
        body=b"{invalid",
        headers={"Content-Type": "application/json", "Content-Length": "8"},
    )
    resp = conn.getresponse()
    assert resp.status == 400
    data = json.loads(resp.read())
    assert data["code"] == "INVALID_JSON"
    conn.close()


def test_validate_missing_latex(mock_server):
    conn = http.client.HTTPConnection(mock_server[0], mock_server[1])
    conn.request(
        "POST",
        "/validate",
        body=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "2"},
    )
    resp = conn.getresponse()
    assert resp.status == 400
    data = json.loads(resp.read())
    assert data["code"] == "INVALID_REQUEST"
    conn.close()


def test_validate_unknown_engine(mock_server):
    conn = http.client.HTTPConnection(mock_server[0], mock_server[1])
    body = json.dumps({"latex": "x", "engines": ["nosuch"]})
    conn.request(
        "POST",
        "/validate",
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    resp = conn.getresponse()
    assert resp.status == 422
    data = json.loads(resp.read())
    assert data["code"] == "UNKNOWN_ENGINE"
    conn.close()


def test_compute_unavailable_engine(mock_server):
    class UnavailEngine(BaseEngine):
        name = "unavail"

        def validate(self, latex):
            return EngineResult(engine="unavail", success=False)

        def is_available(self):
            return False

        @property
        def capabilities(self):
            return [Capability.COMPUTE]

    cas_main.ENGINES["unavail"] = UnavailEngine()

    conn = http.client.HTTPConnection(mock_server[0], mock_server[1])
    body = json.dumps(
        {"engine": "unavail", "task_type": "template", "template": "eval", "inputs": {}}
    )

    conn.request(
        "POST",
        "/compute",
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    resp = conn.getresponse()
    assert resp.status == 503
    data = json.loads(resp.read())
    assert data["code"] == "ENGINE_UNAVAILABLE"
    conn.close()


@patch("cas_service.main.ThreadPoolExecutor")
def test_init_engines_with_env(mock_executor):
    with patch.dict(
        "os.environ", {"CAS_SYMPY_TIMEOUT": "10", "CAS_DEFAULT_ENGINE": "sympy"}
    ):
        # Mocking sub-engines to avoid real init
        with (
            patch("cas_service.main.SympyEngine"),
            patch("cas_service.main.MatlabEngine"),
            patch("cas_service.main.SageEngine"),
            patch("cas_service.main.WolframAlphaEngine"),
        ):
            cas_main._init_engines()
            assert "sympy" in cas_main.ENGINES


def test_validate_one_exception():
    mock_engine = MagicMock()
    mock_engine.validate.side_effect = Exception("Boom")
    cas_main.ENGINES["fail"] = mock_engine
    result = cas_main._validate_one("fail", "x+1")
    assert result["success"] is False
    assert result["error"] == "Boom"


@patch("cas_service.main.logger")
def test_validate_parallel_exception(mock_logger):
    mock_pool = MagicMock()
    cas_main._validate_pool = mock_pool

    f1 = MagicMock()
    f1.result.side_effect = Exception("Future failed")
    f2 = MagicMock()
    f2.result.side_effect = Exception("Future failed")

    mock_pool.submit.side_effect = [f1, f2]

    cas_main.ENGINES["engine1"] = MagicMock()
    cas_main.ENGINES["engine2"] = MagicMock()

    def mock_as_completed(future_dict):
        return list(future_dict.keys())

    with patch("cas_service.main.as_completed", side_effect=mock_as_completed):
        results = cas_main._validate_parallel(["engine1", "engine2"], "x+1")
        assert results[0]["success"] is False
        assert "Future failed" in results[0]["error"]


def test_json_formatter():
    formatter = cas_main.JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=None,
        exc_info=None,
    )
    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert data["msg"] == "test message"
    assert data["level"] == "INFO"


def test_json_formatter_with_exception():
    formatter = cas_main.JsonFormatter()
    try:
        raise ValueError("Boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="error message",
            args=None,
            exc_info=sys.exc_info(),
        )
    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert "exception" in data
    assert "ValueError: Boom" in data["exception"]


@patch("cas_service.main.HTTPServer")
def test_main_startup_and_shutdown(mock_server_class):
    mock_server_inst = mock_server_class.return_value
    mock_server_inst.serve_forever.side_effect = KeyboardInterrupt()

    with patch.dict("os.environ", {"CAS_LOG_LEVEL": "DEBUG", "CAS_PORT": "8888"}):
        with patch("cas_service.main._init_engines"):
            cas_main.main()

    assert mock_server_inst.server_close.called


def test_handle_engines_with_reason(mock_server):
    class ReasonEngine(BaseEngine):
        name = "reason"

        def validate(self, latex):
            return EngineResult(engine="reason", success=False)

        def is_available(self):
            return False

        @property
        def availability_reason(self):
            return "just because"

    cas_main.ENGINES["reason"] = ReasonEngine()

    status, data = _get(mock_server, "/engines")
    assert status == 200
    engines = {e["name"]: e for e in data["engines"]}
    assert engines["reason"]["availability_reason"] == "just because"


def _get(addr, path):
    import http.client

    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data
