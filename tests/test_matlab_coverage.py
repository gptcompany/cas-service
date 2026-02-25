"""Additional tests for MatlabEngine to increase coverage of error paths."""

from __future__ import annotations

import subprocess
from unittest.mock import patch


from cas_service.engines.matlab_engine import MatlabEngine


class TestMatlabEngineErrorPaths:
    @patch("subprocess.run")
    def test_run_matlab_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["matlab"], timeout=30)
        engine = MatlabEngine()

        # Test validate timeout
        result = engine.validate("x+1")
        assert result.success is False
        assert "timeout" in result.error

    @patch("subprocess.run")
    def test_run_matlab_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        engine = MatlabEngine()

        result = engine.validate("x+1")
        assert result.success is False
        assert "not found" in result.error

    @patch("subprocess.run")
    def test_run_matlab_runtime_error(self, mock_run):
        # Non-zero exit with stderr
        mock_run.return_value = subprocess.CompletedProcess(
            args=["matlab"], returncode=1, stdout="", stderr="Some MATLAB error"
        )
        engine = MatlabEngine()

        result = engine.validate("x+1")
        assert result.success is False
        assert "matlab error" in result.error.lower()

    def test_validate_empty_after_conversion(self):
        engine = MatlabEngine()
        # A string that becomes empty after conversion
        with patch(
            "cas_service.engines.matlab_engine._latex_to_matlab", return_value=""
        ):
            result = engine.validate("something")
            assert result.success is False
            assert "empty expression" in result.error

    @patch("subprocess.run")
    def test_get_version_fail(self, mock_run):
        mock_run.side_effect = Exception("fail")
        engine = MatlabEngine()
        assert "unavailable" in engine.get_version().lower()

    @patch("subprocess.run")
    def test_get_version_no_match(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["matlab"], returncode=0, stdout="No version here", stderr=""
        )
        engine = MatlabEngine()
        assert "unknown" in engine.get_version().lower()

    @patch.object(MatlabEngine, "is_available", return_value=True)
    @patch.object(MatlabEngine, "_run_matlab")
    def test_compute_engine_error_generic_exception(self, mock_run, _avail):
        mock_run.side_effect = Exception("Unexpected")
        engine = MatlabEngine()
        from cas_service.engines.base import ComputeRequest

        req = ComputeRequest(
            engine="matlab",
            task_type="template",
            template="evaluate",
            inputs={"expression": "1"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "ENGINE_ERROR"

    @patch.object(MatlabEngine, "is_available", return_value=True)
    @patch.object(MatlabEngine, "_run_matlab")
    def test_compute_returns_error_tag(self, mock_run, _avail):
        mock_run.return_value = "MATLAB_ERROR: Syntax error in script\n"
        engine = MatlabEngine()
        from cas_service.engines.base import ComputeRequest

        req = ComputeRequest(
            engine="matlab",
            task_type="template",
            template="evaluate",
            inputs={"expression": "1"},
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error == "Syntax error in script"
        assert result.error_code == "ENGINE_ERROR"
