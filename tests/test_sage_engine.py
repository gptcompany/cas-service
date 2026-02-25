"""Tests for SageEngine — validate + compute, input validation, error handling."""

from __future__ import annotations

import json
import shutil
from http.server import HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from cas_service.engines.base import Capability, ComputeRequest
from cas_service.engines.sage_engine import (
    SageEngine,
    _latex_to_sage,
    _validate_input,
)
from cas_service.runtime.executor import ExecResult


# ---------------------------------------------------------------------------
# LaTeX → Sage conversion
# ---------------------------------------------------------------------------


class TestLatexToSage:
    def test_frac(self):
        assert _latex_to_sage(r"\frac{a}{b}") == "((a)/(b))"

    def test_sqrt(self):
        assert _latex_to_sage(r"\sqrt{x}") == "sqrt(x)"

    def test_nth_root(self):
        assert _latex_to_sage(r"\sqrt[3]{x}") == "(x)^(1/(3))"

    def test_trig(self):
        assert _latex_to_sage(r"\sin") == "sin"
        assert _latex_to_sage(r"\cos") == "cos"

    def test_pi(self):
        assert _latex_to_sage(r"\pi") == "pi"

    def test_implicit_mult(self):
        assert _latex_to_sage("2x") == "2*x"

    def test_power_braces(self):
        assert _latex_to_sage(r"x^{2}") == "x^(2)"

    def test_left_right_removed(self):
        assert _latex_to_sage(r"\left(\right)") == "()"


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------


class TestEquationRegex:
    """Tests for equation detection regex — verifies == is not converted to ===."""

    def test_double_equals_preserved(self):
        """== in expression should not be touched by equation conversion."""
        engine = SageEngine()
        engine._available = True
        # Directly test the regex used in validate
        import re

        sage_expr = "x == 1"
        # Should detect == and set is_equation True without substitution
        assert "==" in sage_expr
        assert not re.search(r"(?<![<>!=])=(?!=)", sage_expr)

    def test_single_equals_converted(self):
        """Single = should be converted to ==."""
        import re

        sage_expr = "x = 1"
        match = re.search(r"(?<![<>!=])=(?!=)", sage_expr)
        assert match is not None
        converted = re.sub(r"(?<![<>!=])=(?!=)", "==", sage_expr)
        assert converted == "x == 1"

    def test_gte_lte_not_converted(self):
        """>=, <=, != should not be affected."""
        import re

        for expr in ["x >= 1", "x <= 1", "x != 1"]:
            match = re.search(r"(?<![<>!=])=(?!=)", expr)
            assert match is None, f"Unexpectedly matched in: {expr}"

    def test_valid_expression(self):
        assert _validate_input("x^2 + 1") is True

    def test_empty_rejected(self):
        assert _validate_input("") is False

    def test_too_long_rejected(self):
        assert _validate_input("x" * 501) is False

    def test_import_blocked(self):
        assert _validate_input("__import__('os')") is False

    def test_exec_blocked(self):
        assert _validate_input("exec('code')") is False

    def test_os_blocked(self):
        assert _validate_input("os.system('ls')") is False

    def test_null_byte_rejected(self):
        assert _validate_input("x\x00y") is False

    def test_safe_math(self):
        assert _validate_input("sin(x) + cos(y)") is True


# ---------------------------------------------------------------------------
# Unit tests — SageEngine capabilities
# ---------------------------------------------------------------------------


class TestSageEngineCapabilities:
    def test_capabilities(self):
        engine = SageEngine()
        assert Capability.VALIDATE in engine.capabilities
        assert Capability.COMPUTE in engine.capabilities

    def test_available_templates(self):
        templates = SageEngine.available_templates()
        assert "evaluate" in templates
        assert "simplify" in templates
        assert "solve" in templates
        assert "factor" in templates
        assert "integrate" in templates
        assert "differentiate" in templates
        assert "matrix_rank" in templates
        assert "latex_to_sage" in templates
        assert "group_order" in templates
        assert "is_abelian" in templates
        assert "center_size" in templates
        assert len(templates) == 11


# ---------------------------------------------------------------------------
# Unit tests — unavailable engine
# ---------------------------------------------------------------------------


class TestSageEngineUnavailable:
    def test_validate_when_unavailable(self):
        engine = SageEngine(sage_path="/nonexistent/sage")
        result = engine.validate("x^2")
        assert result.success is False
        assert "not found" in (result.error or "")

    def test_compute_when_unavailable(self):
        engine = SageEngine(sage_path="/nonexistent/sage")
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="evaluate",
            inputs={"expression": "x^2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Unit tests — compute template errors (mocked availability)
# ---------------------------------------------------------------------------


class TestSageTemplateErrors:
    @patch.object(SageEngine, "is_available", return_value=True)
    def test_unknown_template(self, _mock):
        engine = SageEngine()
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="nonexistent",
            inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "UNKNOWN_TEMPLATE"

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_missing_input(self, _mock):
        engine = SageEngine()
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="evaluate",
            inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_invalid_input_value(self, _mock):
        engine = SageEngine()
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="evaluate",
            inputs={"expression": "__import__('os').system('ls')"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# Unit tests — mocked subprocess execution
# ---------------------------------------------------------------------------


class TestSageEngineExecution:
    @patch.object(SageEngine, "is_available", return_value=True)
    def test_successful_validate(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SAGE_VALID:1\nSAGE_SIMPLIFIED:x^2 + 1\nSAGE_PARSED:x^2 + 1\n",
            stderr="",
            time_ms=100,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("x^2 + 1")
        assert result.success is True
        assert result.is_valid is True
        assert result.simplified == "x^2 + 1"

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_invalid_expression(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SAGE_VALID:0\nSAGE_ERROR:malformed expression\n",
            stderr="",
            time_ms=50,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("\\invalid{}")
        assert result.success is False  # error in parsing

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_timeout(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=-1,
            stdout="",
            stderr="timed out",
            time_ms=30000,
            timed_out=True,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("x^2")
        assert result.success is False
        assert "timed out" in (result.error or "")

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_successful_compute_evaluate(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SAGE_RESULT:42\n",
            stderr="",
            time_ms=200,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="evaluate",
            inputs={"expression": "6*7"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "42"}

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_compute_engine_error(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=1,
            stdout="",
            stderr="Sage crashed",
            time_ms=100,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="evaluate",
            inputs={"expression": "x^2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_ERROR"


# ---------------------------------------------------------------------------
# Integration tests — real Sage subprocess (skip if not installed)
# ---------------------------------------------------------------------------

_sage_available = shutil.which("sage") is not None


@pytest.mark.skipif(not _sage_available, reason="SageMath not installed")
class TestSageIntegrationValidate:
    def test_validate_simple_expression(self):
        engine = SageEngine(timeout=60)
        result = engine.validate("x^2 + 1")
        assert result.success is True
        assert result.is_valid is True
        assert result.simplified is not None

    def test_validate_trig(self):
        engine = SageEngine(timeout=60)
        result = engine.validate("sin(x)^2 + cos(x)^2")
        assert result.success is True
        assert result.is_valid is True


@pytest.mark.skipif(not _sage_available, reason="SageMath not installed")
class TestSageIntegrationCompute:
    def test_evaluate(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="evaluate",
            inputs={"expression": "2^10"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result["value"] == "1024"

    def test_simplify(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="simplify",
            inputs={"expression": "(x^2 + 2*x + 1)/(x + 1)"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "x + 1" in result.result["value"]

    def test_factor(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="factor",
            inputs={"expression": "x^2 - 1"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "(x - 1)" in result.result["value"]
        assert "(x + 1)" in result.result["value"]

    def test_solve(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="solve",
            inputs={"equation": "x^2 - 4", "variable": "x"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "2" in result.result["value"]
        assert "-2" in result.result["value"]

    def test_differentiate(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="differentiate",
            inputs={"expression": "x^3", "variable": "x"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "3*x^2" in result.result["value"]

    def test_integrate(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="integrate",
            inputs={"expression": "2*x", "variable": "x"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "x^2" in result.result["value"]

    def test_latex_to_sage(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="latex_to_sage",
            inputs={"expression": "x^2 + 1"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "x^2" in result.result["value"]

    def test_group_order(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="group_order",
            inputs={"group_expr": "SymmetricGroup(3)"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result["value"] == "6"

    def test_is_abelian(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="is_abelian",
            inputs={"group_expr": "SymmetricGroup(3)"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result["value"] == "False"

    def test_center_size(self):
        engine = SageEngine(timeout=60)
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="center_size",
            inputs={"group_expr": "SymmetricGroup(3)"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result["value"] == "1"


# ---------------------------------------------------------------------------
# Unit tests — mocked group theory templates
# ---------------------------------------------------------------------------


class TestSageGroupTheoryMocked:
    @patch.object(SageEngine, "is_available", return_value=True)
    def test_group_order_mocked(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SAGE_RESULT:6\n",
            stderr="",
            time_ms=200,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="group_order",
            inputs={"group_expr": "SymmetricGroup(3)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "6"}

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_is_abelian_mocked(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SAGE_RESULT:False\n",
            stderr="",
            time_ms=200,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="is_abelian",
            inputs={"group_expr": "SymmetricGroup(3)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "False"}

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_center_size_mocked(self, _avail):
        engine = SageEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SAGE_RESULT:1\n",
            stderr="",
            time_ms=200,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="center_size",
            inputs={"group_expr": "SymmetricGroup(3)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "1"}

    @patch.object(SageEngine, "is_available", return_value=True)
    def test_group_order_missing_input(self, _avail):
        engine = SageEngine()
        req = ComputeRequest(
            engine="sage",
            task_type="template",
            template="group_order",
            inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def cas_server_with_sage():
    """Start CAS server with a mock-available Sage engine."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    cas_main.ENGINES.clear()

    sage = SageEngine()
    sage._available = True
    cas_main.ENGINES["sage"] = sage

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

    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=10)
    conn.request(
        "POST",
        path,
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

    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data


class TestSageHTTPIntegration:
    def test_sage_in_engines_list(self, cas_server_with_sage):
        status, data = _get(cas_server_with_sage, "/engines")
        assert status == 200
        names = [e["name"] for e in data["engines"]]
        assert "sage" in names
        sage = next(e for e in data["engines"] if e["name"] == "sage")
        assert "validate" in sage["capabilities"]
        assert "compute" in sage["capabilities"]

    @pytest.mark.skipif(not _sage_available, reason="SageMath not installed")
    def test_compute_via_http(self, cas_server_with_sage):
        status, data = _post(
            cas_server_with_sage,
            "/compute",
            {
                "engine": "sage",
                "task_type": "template",
                "template": "evaluate",
                "inputs": {"expression": "2^10"},
                "timeout_s": 60,
            },
        )
        assert status == 200
        assert data["success"] is True
        assert data["result"]["value"] == "1024"

    def test_compute_unknown_template_via_http(self, cas_server_with_sage):
        status, data = _post(
            cas_server_with_sage,
            "/compute",
            {
                "engine": "sage",
                "task_type": "template",
                "template": "nonexistent",
            },
        )
        assert status == 200
        assert data["success"] is False
        assert data["error_code"] == "UNKNOWN_TEMPLATE"
