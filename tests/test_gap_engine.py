"""Tests for GapEngine (Slice B) — template compute, input validation, error handling."""

from __future__ import annotations

import json
import shutil
import subprocess
from http.server import HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from cas_service.engines.base import Capability, ComputeRequest, ComputeResult
from cas_service.engines.gap_engine import GapEngine, _validate_input


# ---------------------------------------------------------------------------
# Unit tests — GapEngine directly
# ---------------------------------------------------------------------------


class TestGapEngineCapabilities:

    def test_capabilities_is_compute(self):
        engine = GapEngine()
        assert engine.capabilities == [Capability.COMPUTE]

    def test_validate_returns_not_supported(self):
        engine = GapEngine()
        result = engine.validate("x^2")
        assert result.success is False
        assert "does not support" in (result.error or "")

    def test_available_templates(self):
        templates = GapEngine.available_templates()
        assert "group_order" in templates
        assert "is_abelian" in templates
        assert "center_size" in templates


class TestGapInputValidation:

    def test_valid_simple_function(self):
        assert _validate_input("SymmetricGroup(4)") is True

    def test_valid_number(self):
        assert _validate_input("42") is True

    def test_empty_rejected(self):
        assert _validate_input("") is False

    def test_too_long_rejected(self):
        assert _validate_input("a" * 201) is False

    def test_semicolon_rejected(self):
        assert _validate_input("Exec(command);") is False

    def test_newline_rejected(self):
        assert _validate_input("foo\nbar") is False

    def test_exec_blocked(self):
        assert _validate_input("Exec(\"ls\")") is False

    def test_io_blocked(self):
        assert _validate_input("IO_File(\"foo\")") is False

    def test_process_blocked(self):
        assert _validate_input("Process(\"bash\")") is False


class TestGapEngineUnavailable:

    def test_compute_when_unavailable(self):
        engine = GapEngine(gap_path="/nonexistent/gap")
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="group_order",
            inputs={"group_expr": "SymmetricGroup(4)"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_UNAVAILABLE"


class TestGapEngineTemplateErrors:

    @patch.object(GapEngine, "is_available", return_value=True)
    def test_unknown_template(self, _mock):
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="nonexistent", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "UNKNOWN_TEMPLATE"

    @patch.object(GapEngine, "is_available", return_value=True)
    def test_missing_input(self, _mock):
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="group_order", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"

    @patch.object(GapEngine, "is_available", return_value=True)
    def test_invalid_input_value(self, _mock):
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="group_order",
            inputs={"group_expr": "Exec(\"rm -rf /\")"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"


class TestGapEngineExecution:

    @patch("cas_service.engines.gap_engine.subprocess.run")
    @patch.object(GapEngine, "is_available", return_value=True)
    def test_successful_compute(self, _avail, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="24\n", stderr="",
        )
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="group_order",
            inputs={"group_expr": "SymmetricGroup(4)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "24"}
        assert result.engine == "gap"

    @patch("cas_service.engines.gap_engine.subprocess.run")
    @patch.object(GapEngine, "is_available", return_value=True)
    def test_gap_error_exit(self, _avail, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error in GAP",
        )
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="group_order",
            inputs={"group_expr": "SymmetricGroup(4)"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_ERROR"

    @patch("cas_service.engines.gap_engine.subprocess.run")
    @patch.object(GapEngine, "is_available", return_value=True)
    def test_timeout(self, _avail, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gap", timeout=5)
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="group_order",
            inputs={"group_expr": "SymmetricGroup(100)"},
            timeout_s=5,
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "TIMEOUT"

    @patch("cas_service.engines.gap_engine.subprocess.run")
    @patch.object(GapEngine, "is_available", return_value=True)
    def test_is_abelian_template(self, _avail, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="true\n", stderr="",
        )
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="is_abelian",
            inputs={"group_expr": "CyclicGroup(5)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "true"}

    @patch("cas_service.engines.gap_engine.subprocess.run")
    @patch.object(GapEngine, "is_available", return_value=True)
    def test_center_size_template(self, _avail, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1\n", stderr="",
        )
        engine = GapEngine()
        req = ComputeRequest(
            engine="gap", task_type="template",
            template="center_size",
            inputs={"group_expr": "SymmetricGroup(4)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "1"}


# ---------------------------------------------------------------------------
# Integration tests — via HTTP server with GAP engine
# ---------------------------------------------------------------------------


@pytest.fixture()
def cas_server_with_gap():
    """Start CAS server with a mock-available GAP engine."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    cas_main.ENGINES.clear()

    gap = GapEngine()
    # Force available for integration tests
    gap._available = True
    cas_main.ENGINES["gap"] = gap

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)


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


def _get(addr, path):
    import http.client
    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data


class TestGapHTTPIntegration:

    def test_gap_in_engines_list(self, cas_server_with_gap):
        status, data = _get(cas_server_with_gap, "/engines")
        assert status == 200
        names = [e["name"] for e in data["engines"]]
        assert "gap" in names
        gap = next(e for e in data["engines"] if e["name"] == "gap")
        assert "compute" in gap["capabilities"]
        assert "validate" not in gap["capabilities"]

    @patch("cas_service.engines.gap_engine.subprocess.run")
    def test_compute_via_http(self, mock_run, cas_server_with_gap):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="24\n", stderr="",
        )
        status, data = _post(cas_server_with_gap, "/compute", {
            "engine": "gap",
            "task_type": "template",
            "template": "group_order",
            "inputs": {"group_expr": "SymmetricGroup(4)"},
        })
        assert status == 200
        assert data["success"] is True
        assert data["result"]["value"] == "24"

    def test_compute_unknown_template_via_http(self, cas_server_with_gap):
        status, data = _post(cas_server_with_gap, "/compute", {
            "engine": "gap",
            "task_type": "template",
            "template": "nonexistent",
        })
        # Engine returns error via ComputeResult (success=False), HTTP 200
        assert status == 200
        assert data["success"] is False
        assert data["error_code"] == "UNKNOWN_TEMPLATE"

    def test_compute_missing_input_via_http(self, cas_server_with_gap):
        status, data = _post(cas_server_with_gap, "/compute", {
            "engine": "gap",
            "task_type": "template",
            "template": "group_order",
            "inputs": {},
        })
        assert status == 200
        assert data["success"] is False
        assert data["error_code"] == "MISSING_INPUT"
