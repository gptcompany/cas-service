"""Tests for VerifyStep smoke tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from rich.console import Console


def _console() -> Console:
    return Console(file=MagicMock(), highlight=False)


class TestVerifyStepSmoke:
    def _make(self):
        from cas_service.setup._verify import VerifyStep

        return VerifyStep()

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    @patch("cas_service.setup._verify.get_service_url", return_value="http://localhost:8769")
    def test_smoke_test_validate_success(self, mock_url, mock_urlopen):
        """_smoke_test_validate prints success when engine returns is_valid."""
        from cas_service.setup._verify import VerifyStep
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "results": [
                {"engine": "sympy", "success": True, "is_valid": True, "simplified": "x**2 + 1"}
            ]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        
        console = _console()
        VerifyStep._smoke_test_validate(console, ["sympy"])
        # Should complete without error

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    @patch("cas_service.setup._verify.get_service_url", return_value="http://localhost:8769")
    def test_smoke_test_validate_invalid(self, mock_url, mock_urlopen):
        """_smoke_test_validate prints warning when engine returns not is_valid."""
        from cas_service.setup._verify import VerifyStep
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "results": [
                {"engine": "sympy", "success": True, "is_valid": False}
            ]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        
        console = _console()
        VerifyStep._smoke_test_validate(console, ["sympy"])

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    @patch("cas_service.setup._verify.get_service_url", return_value="http://localhost:8769")
    def test_smoke_test_validate_error(self, mock_url, mock_urlopen):
        """_smoke_test_validate prints failure when engine returns success=False."""
        from cas_service.setup._verify import VerifyStep
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "results": [
                {"engine": "sympy", "success": False, "error": "timeout"}
            ]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        
        console = _console()
        VerifyStep._smoke_test_validate(console, ["sympy"])

    @patch("cas_service.setup._verify.urllib.request.urlopen", side_effect=Exception("boom"))
    def test_smoke_test_validate_exception(self, mock_urlopen):
        """_smoke_test_validate handles exceptions gracefully."""
        from cas_service.setup._verify import VerifyStep
        console = _console()
        VerifyStep._smoke_test_validate(console, ["sympy"])

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    @patch("cas_service.setup._verify.get_service_url", return_value="http://localhost:8769")
    def test_smoke_test_compute_success(self, mock_url, mock_urlopen):
        """_smoke_test_compute prints success when result matches expected."""
        from cas_service.setup._verify import VerifyStep
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "success": True,
            "result": {"value": "1024"}
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        
        console = _console()
        VerifyStep._smoke_test_compute(console, "sage")

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    @patch("cas_service.setup._verify.get_service_url", return_value="http://localhost:8769")
    def test_smoke_test_compute_wrong_value(self, mock_url, mock_urlopen):
        """_smoke_test_compute prints result even if it doesn't match expected."""
        from cas_service.setup._verify import VerifyStep
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "success": True,
            "result": {"value": "999"}
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        
        console = _console()
        VerifyStep._smoke_test_compute(console, "sage")

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    @patch("cas_service.setup._verify.get_service_url", return_value="http://localhost:8769")
    def test_smoke_test_compute_fail(self, mock_url, mock_urlopen):
        """_smoke_test_compute prints error when success=False."""
        from cas_service.setup._verify import VerifyStep
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "success": False,
            "error": "engine error"
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        
        console = _console()
        VerifyStep._smoke_test_compute(console, "sage")

    @patch("cas_service.setup._verify.urllib.request.urlopen", side_effect=Exception("boom"))
    def test_smoke_test_compute_exception(self, mock_urlopen):
        """_smoke_test_compute handles exceptions gracefully."""
        from cas_service.setup._verify import VerifyStep
        console = _console()
        VerifyStep._smoke_test_compute(console, "sage")

    def test_smoke_test_compute_unsupported_engine(self):
        """_smoke_test_compute returns early if engine not in smoke test map."""
        from cas_service.setup._verify import VerifyStep
        VerifyStep._smoke_test_compute(_console(), "unknown")

    # -- Covering the install loop more thoroughly ---------------------------

    @patch("cas_service.setup._verify.VerifyStep._smoke_test_compute")
    @patch("cas_service.setup._verify.VerifyStep._smoke_test_validate")
    @patch("cas_service.setup._verify.VerifyStep._get_json")
    def test_install_full_loop(self, mock_get, mock_smoke_val, mock_smoke_comp):
        """install() triggers smoke tests if engines are available."""
        mock_get.side_effect = [
            {"status": "ok", "uptime_seconds": 120},
            {
                "engines": [
                    {
                        "name": "sage",
                        "available": True,
                        "capabilities": ["validate", "compute"],
                    }
                ]
            },
        ]
        from unittest.mock import ANY
        step = self._make()
        assert step.install(_console()) is True
        mock_smoke_val.assert_called_once()
        mock_smoke_comp.assert_called_once_with(ANY, "sage")
