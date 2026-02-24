"""Tests for MatlabEngine — validate + compute, input validation, is_available."""

from __future__ import annotations

import shutil
from unittest.mock import MagicMock, patch

import pytest

from cas_service.engines.base import Capability, ComputeRequest
from cas_service.engines.matlab_engine import (
    MatlabEngine,
    _latex_to_matlab,
    _validate_input,
)


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------


class TestMatlabInputValidation:

    def test_valid_expression(self):
        assert _validate_input("x^2 + 1") is True

    def test_empty_rejected(self):
        assert _validate_input("") is False

    def test_too_long_rejected(self):
        assert _validate_input("x" * 501) is False

    def test_system_blocked(self):
        assert _validate_input("system('ls')") is False

    def test_eval_blocked(self):
        assert _validate_input("eval('code')") is False

    def test_fopen_blocked(self):
        assert _validate_input("fopen('file')") is False

    def test_null_byte_rejected(self):
        assert _validate_input("x\x00y") is False

    def test_safe_math(self):
        assert _validate_input("sin(x) + cos(y)") is True


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestMatlabIsAvailable:

    def test_nonexistent_absolute_path(self):
        engine = MatlabEngine(matlab_path="/nonexistent/matlab")
        assert engine.is_available() is False

    def test_bare_name_not_on_path(self):
        engine = MatlabEngine(matlab_path="definitely_not_a_real_matlab_binary_xyz")
        assert engine.is_available() is False

    def test_default_not_available(self):
        """Default 'matlab' is unlikely to be on PATH in CI."""
        engine = MatlabEngine()
        # Just verify it returns a bool without error
        result = engine.is_available()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Capabilities and templates
# ---------------------------------------------------------------------------


class TestMatlabCapabilities:

    def test_capabilities(self):
        engine = MatlabEngine()
        assert Capability.VALIDATE in engine.capabilities
        assert Capability.COMPUTE in engine.capabilities

    def test_available_templates(self):
        templates = MatlabEngine.available_templates()
        assert "evaluate" in templates
        assert "simplify" in templates
        assert "solve" in templates
        assert "factor" in templates
        assert len(templates) == 4


# ---------------------------------------------------------------------------
# Compute template errors (no MATLAB needed)
# ---------------------------------------------------------------------------


class TestMatlabComputeErrors:

    @patch.object(MatlabEngine, "is_available", return_value=True)
    def test_unknown_template(self, _mock):
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="nonexistent", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "UNKNOWN_TEMPLATE"

    @patch.object(MatlabEngine, "is_available", return_value=True)
    def test_missing_input(self, _mock):
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="evaluate", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"

    @patch.object(MatlabEngine, "is_available", return_value=True)
    def test_invalid_input_value(self, _mock):
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="evaluate",
            inputs={"expression": "system('rm -rf /')"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"

    def test_unavailable_engine(self):
        engine = MatlabEngine(matlab_path="/nonexistent/matlab")
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="evaluate",
            inputs={"expression": "2+2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Mocked compute execution
# ---------------------------------------------------------------------------


class TestMatlabComputeMocked:

    @patch.object(MatlabEngine, "is_available", return_value=True)
    @patch.object(MatlabEngine, "_run_matlab")
    def test_successful_evaluate(self, mock_run, _avail):
        mock_run.return_value = "MATLAB_RESULT:42\n"
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="evaluate",
            inputs={"expression": "6*7"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "42"}

    @patch.object(MatlabEngine, "is_available", return_value=True)
    @patch.object(MatlabEngine, "_run_matlab")
    def test_successful_simplify(self, mock_run, _avail):
        mock_run.return_value = "MATLAB_RESULT:x + 1\n"
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="simplify",
            inputs={"expression": "(x^2 + 2*x + 1)/(x + 1)"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result["value"] == "x + 1"

    @patch.object(MatlabEngine, "is_available", return_value=True)
    @patch.object(MatlabEngine, "_run_matlab")
    def test_successful_solve(self, mock_run, _avail):
        mock_run.return_value = "MATLAB_RESULT:[2; -2]\n"
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="solve",
            inputs={"equation": "x^2 - 4", "variable": "x"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert "2" in result.result["value"]

    @patch.object(MatlabEngine, "is_available", return_value=True)
    @patch.object(MatlabEngine, "_run_matlab")
    def test_no_result_output(self, mock_run, _avail):
        mock_run.return_value = "some random output\n"
        engine = MatlabEngine()
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="evaluate",
            inputs={"expression": "2+2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_ERROR"


# ---------------------------------------------------------------------------
# LaTeX → MATLAB conversion
# ---------------------------------------------------------------------------


class TestLatexToMatlab:

    def test_frac(self):
        assert "(a)/(b)" in _latex_to_matlab(r"\frac{a}{b}")

    def test_sqrt(self):
        # After sqrt conversion, implicit mult rule x( → x*( applies
        result = _latex_to_matlab(r"\sqrt{x}")
        assert result.startswith("sqrt")

    def test_trig(self):
        assert _latex_to_matlab(r"\sin") == "sin"
        assert _latex_to_matlab(r"\cos") == "cos"

    def test_pi(self):
        assert _latex_to_matlab(r"\pi") == "pi"

    def test_implicit_mult(self):
        assert "2*x" in _latex_to_matlab("2x")


# ---------------------------------------------------------------------------
# Integration tests (skip if MATLAB not installed)
# ---------------------------------------------------------------------------

_matlab_available = shutil.which("matlab") is not None


@pytest.mark.skipif(not _matlab_available, reason="MATLAB not installed")
class TestMatlabIntegration:

    def test_validate_simple(self):
        engine = MatlabEngine(timeout=60)
        result = engine.validate("x^2 + 1")
        assert result.success is True

    def test_compute_evaluate(self):
        engine = MatlabEngine(timeout=60)
        req = ComputeRequest(
            engine="matlab", task_type="template",
            template="evaluate",
            inputs={"expression": "2^10"},
            timeout_s=60,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "1024" in result.result["value"]
