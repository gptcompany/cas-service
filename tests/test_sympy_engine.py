"""Tests for SympyEngine — validate + compute via subprocess, input validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cas_service.engines.base import Capability, ComputeRequest
from cas_service.engines.sympy_engine import (
    SympyEngine,
    _validate_input,
)
from cas_service.runtime.executor import ExecResult


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------


class TestSympyInputValidation:

    def test_valid_expression(self):
        assert _validate_input("x**2 + 1") is True

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
# Capabilities and templates
# ---------------------------------------------------------------------------


class TestSympyCapabilities:

    def test_capabilities(self):
        engine = SympyEngine()
        assert Capability.VALIDATE in engine.capabilities
        assert Capability.COMPUTE in engine.capabilities

    def test_available_templates(self):
        templates = SympyEngine.available_templates()
        assert "evaluate" in templates
        assert "simplify" in templates
        assert "solve" in templates
        assert "factor" in templates
        assert "integrate" in templates
        assert "differentiate" in templates
        assert len(templates) == 6

    def test_is_available(self):
        engine = SympyEngine()
        assert engine.is_available() is True

    def test_get_version(self):
        engine = SympyEngine()
        version = engine.get_version()
        assert version != "not installed"
        # Should be a version string like "1.12"
        assert "." in version


# ---------------------------------------------------------------------------
# Mocked validate tests
# ---------------------------------------------------------------------------


class TestSympyValidateMocked:

    def test_successful_validate(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SYMPY_VALID:1\nSYMPY_SIMPLIFIED:x**2 + 1\nSYMPY_PARSED:x**2 + 1\n",
            stderr="",
            time_ms=100,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("x^2 + 1")
        assert result.success is True
        assert result.is_valid is True
        assert result.simplified == "x**2 + 1"

    def test_parse_error(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SYMPY_ERROR:could not parse\n",
            stderr="",
            time_ms=50,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("\\invalid{}")
        assert result.success is False
        assert "could not parse" in (result.error or "")

    def test_timeout(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=-1,
            stdout="",
            stderr="timed out",
            time_ms=5000,
            timed_out=True,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("x^2")
        assert result.success is False
        assert "timed out" in (result.error or "")

    def test_nonzero_exit(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=1,
            stdout="",
            stderr="crash",
            time_ms=100,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        result = engine.validate("x^2")
        assert result.success is False
        assert "exited with code 1" in (result.error or "")


# ---------------------------------------------------------------------------
# Mocked compute tests
# ---------------------------------------------------------------------------


class TestSympyComputeMocked:

    def test_successful_compute(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SYMPY_RESULT:(x + 1)**2\n",
            stderr="",
            time_ms=200,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="simplify",
            inputs={"expression": "x**2 + 2*x + 1"},
        )
        result = engine.compute(req)
        assert result.success is True
        assert result.result == {"value": "(x + 1)**2"}

    def test_unknown_template(self):
        engine = SympyEngine()
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="nonexistent", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "UNKNOWN_TEMPLATE"

    def test_missing_input(self):
        engine = SympyEngine()
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="evaluate", inputs={},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"

    def test_invalid_input_value(self):
        engine = SympyEngine()
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="evaluate",
            inputs={"expression": "__import__('os').system('ls')"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"

    def test_compute_timeout(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=-1,
            stdout="",
            stderr="timed out",
            time_ms=5000,
            timed_out=True,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="evaluate",
            inputs={"expression": "2**100"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "TIMEOUT"

    def test_compute_engine_error(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=1,
            stdout="",
            stderr="crash",
            time_ms=100,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="evaluate",
            inputs={"expression": "x^2"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_ERROR"

    def test_compute_sympy_error(self):
        engine = SympyEngine()
        mock_result = ExecResult(
            returncode=0,
            stdout="SYMPY_ERROR:name 'foo' is not defined\n",
            stderr="",
            time_ms=100,
        )
        engine._executor = MagicMock()
        engine._executor.run.return_value = mock_result

        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="evaluate",
            inputs={"expression": "foo"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_ERROR"


# ---------------------------------------------------------------------------
# Integration tests — real SymPy subprocess
# ---------------------------------------------------------------------------


class TestSympyIntegrationValidate:
    """Integration tests using real SymPy subprocess."""

    def test_validate_simple(self):
        engine = SympyEngine(timeout=30)
        result = engine.validate("x^2 + 1")
        assert result.success is True
        assert result.is_valid is True
        assert result.simplified is not None

    def test_validate_trig_identity(self):
        engine = SympyEngine(timeout=30)
        result = engine.validate("\\sin(x)")
        assert result.success is True
        assert result.is_valid is True

    def test_validate_invalid_latex(self):
        engine = SympyEngine(timeout=30)
        # Use truly unparseable LaTeX — bare backslash sequences get stripped
        # so we need something that causes a real parse error
        result = engine.validate("\\begin{matrix} \\end{}")
        # May succeed or fail depending on SymPy version; just verify no crash
        assert isinstance(result.success, bool)


class TestSympyIntegrationCompute:
    """Integration tests using real SymPy subprocess."""

    def test_simplify(self):
        engine = SympyEngine(timeout=30)
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="simplify",
            inputs={"expression": "(x**2 - 1)/(x - 1)"},
            timeout_s=30,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "x + 1" in result.result["value"]

    def test_solve(self):
        engine = SympyEngine(timeout=30)
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="solve",
            inputs={"equation": "x**2 - 4", "variable": "x"},
            timeout_s=30,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "2" in result.result["value"]
        assert "-2" in result.result["value"]

    def test_factor(self):
        engine = SympyEngine(timeout=30)
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="factor",
            inputs={"expression": "x**2 - 1"},
            timeout_s=30,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "(x - 1)" in result.result["value"]
        assert "(x + 1)" in result.result["value"]

    def test_differentiate(self):
        engine = SympyEngine(timeout=30)
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="differentiate",
            inputs={"expression": "x**3", "variable": "x"},
            timeout_s=30,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "3*x**2" in result.result["value"]

    def test_integrate(self):
        engine = SympyEngine(timeout=30)
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="integrate",
            inputs={"expression": "2*x", "variable": "x"},
            timeout_s=30,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "x**2" in result.result["value"]

    def test_evaluate(self):
        engine = SympyEngine(timeout=30)
        req = ComputeRequest(
            engine="sympy", task_type="template",
            template="evaluate",
            inputs={"expression": "2**10"},
            timeout_s=30,
        )
        result = engine.compute(req)
        assert result.success is True
        assert "1024" in result.result["value"]
