"""Tests for CAS Service setup wizard -- steps, runner, and main entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _console() -> Console:
    """Return a no-output Console for testing (avoids terminal pollution)."""
    return Console(file=MagicMock(), highlight=False)


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ===========================================================================
# PythonStep
# ===========================================================================


class TestPythonStep:

    def _make(self):
        from cas_service.setup._python import PythonStep
        return PythonStep()

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_check_all_good(self, mock_which, mock_run):
        """check() returns True when Python >= 3.10, uv exists, dry-run clean."""
        mock_run.return_value = _completed(0, stderr="Audited 12 packages")
        step = self._make()
        assert step.check() is True
        mock_which.assert_called_once_with("uv")
        mock_run.assert_called_once()

    @patch("cas_service.setup._python.shutil.which", return_value=None)
    def test_check_no_uv(self, mock_which):
        """check() returns False when uv is missing."""
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_check_needs_install(self, mock_which, mock_run):
        """check() returns False when uv sync dry-run shows packages to install."""
        mock_run.return_value = _completed(0, stderr="Would install sympy-1.13")
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._python.subprocess.run", side_effect=OSError("boom"))
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_check_exception(self, mock_which, mock_run):
        """check() returns False on subprocess exception."""
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._python.sys")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_check_old_python(self, mock_which, mock_sys):
        """check() returns False when Python version is < 3.10."""
        mock_sys.version_info = (3, 9)
        step = self._make()
        assert step.check() is False

    # -- install -------------------------------------------------------------

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_install_success(self, mock_which, mock_run):
        """install() runs uv sync and returns True on success."""
        mock_run.return_value = _completed(0)
        step = self._make()
        assert step.install(_console()) is True

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_install_uv_sync_fails(self, mock_which, mock_run):
        """install() returns False when uv sync returns non-zero."""
        mock_run.return_value = _completed(1, stderr="error: lock file mismatch")
        step = self._make()
        assert step.install(_console()) is False

    @patch("cas_service.setup._python.subprocess.run", side_effect=OSError("timeout"))
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_install_exception(self, mock_which, mock_run):
        """install() returns False on subprocess exception."""
        step = self._make()
        assert step.install(_console()) is False

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value=None)
    def test_install_uv_missing_then_pip_installs(self, mock_which, mock_run):
        """install() tries pip install uv, then uv sync."""
        mock_run.side_effect = [
            _completed(0),  # pip install uv
            _completed(0),  # uv sync
        ]
        step = self._make()
        assert step.install(_console()) is True
        assert mock_run.call_count == 2

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value=None)
    def test_install_pip_install_uv_fails(self, mock_which, mock_run):
        """install() returns False when pip install uv fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "pip")
        step = self._make()
        assert step.install(_console()) is False

    # -- verify --------------------------------------------------------------

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_verify_success(self, mock_which, mock_run):
        """verify() returns True when uv run python succeeds."""
        mock_run.return_value = _completed(0, stdout="3.11.5")
        step = self._make()
        assert step.verify() is True

    @patch("cas_service.setup._python.subprocess.run")
    @patch("cas_service.setup._python.shutil.which", return_value="/usr/bin/uv")
    def test_verify_fails(self, mock_which, mock_run):
        """verify() returns False when uv run python fails."""
        mock_run.return_value = _completed(1)
        step = self._make()
        assert step.verify() is False


# ===========================================================================
# MatlabStep
# ===========================================================================


class TestMatlabStep:

    def _make(self):
        from cas_service.setup._matlab import MatlabStep
        return MatlabStep()

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._matlab.os.access", return_value=True)
    @patch("cas_service.setup._matlab.os.path.isfile", return_value=True)
    @patch("cas_service.setup._matlab.glob.glob", return_value=["/usr/local/MATLAB/R2025a/bin/matlab"])
    def test_check_found_direct_path(self, mock_glob, mock_isfile, mock_access):
        """check() returns True when MATLAB found at a standard path."""
        step = self._make()
        assert step.check() is True
        assert step._found_path is not None

    @patch("cas_service.setup._matlab.os.access", return_value=False)
    @patch("cas_service.setup._matlab.os.path.isfile", return_value=False)
    @patch("cas_service.setup._matlab.glob.glob", return_value=[])
    def test_check_not_found(self, mock_glob, mock_isfile, mock_access):
        """check() returns False when MATLAB is not found anywhere."""
        step = self._make()
        assert step.check() is False
        assert step._found_path is None

    @patch("cas_service.setup._matlab.os.access", return_value=True)
    @patch("cas_service.setup._matlab.os.path.isfile", return_value=True)
    @patch("cas_service.setup._matlab.glob.glob")
    def test_check_found_via_glob(self, mock_glob, mock_isfile, mock_access):
        """check() finds MATLAB via glob pattern expansion."""
        mock_glob.return_value = ["/usr/local/MATLAB/R2025a/bin/matlab"]
        step = self._make()
        assert step.check() is True

    # -- install -------------------------------------------------------------

    def test_install_custom_path_valid(self):
        """install() accepts a valid custom MATLAB path."""
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = "/opt/matlab/bin/matlab"
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_questionary}), \
             patch("cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None), \
             patch("cas_service.setup._matlab.os.path.isfile", return_value=True), \
             patch("cas_service.setup._matlab.os.access", return_value=True):
            assert step.install(_console()) is True
            assert step._found_path == "/opt/matlab/bin/matlab"

    def test_install_custom_path_invalid(self):
        """install() returns False for invalid custom path."""
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = "/nope/matlab"
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_questionary}), \
             patch("cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None), \
             patch("cas_service.setup._matlab.os.path.isfile", return_value=False):
            assert step.install(_console()) is False

    def test_install_user_skips(self):
        """install() returns False when user presses Enter (empty path)."""
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = ""
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_questionary}), \
             patch("cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None):
            assert step.install(_console()) is False

    def test_install_questionary_unavailable(self):
        """install() returns False gracefully when questionary is not installed."""
        step = self._make()
        # Simulate questionary not being importable inside install()
        with patch.dict("sys.modules", {"questionary": None}), \
             patch("cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None):
            # When module is None in sys.modules, import raises ImportError
            assert step.install(_console()) is False

    # -- verify --------------------------------------------------------------

    def test_verify_with_found_path(self):
        """verify() returns True when _found_path is set and executable."""
        step = self._make()
        step._found_path = "/opt/matlab/bin/matlab"
        with patch("cas_service.setup._matlab.os.path.isfile", return_value=True), \
             patch("cas_service.setup._matlab.os.access", return_value=True):
            assert step.verify() is True

    def test_verify_no_path(self):
        """verify() returns False when no MATLAB path was found."""
        step = self._make()
        assert step._found_path is None
        assert step.verify() is False

    def test_verify_path_not_executable(self):
        """verify() returns False when path exists but is not executable."""
        step = self._make()
        step._found_path = "/opt/matlab/bin/matlab"
        with patch("cas_service.setup._matlab.os.path.isfile", return_value=True), \
             patch("cas_service.setup._matlab.os.access", return_value=False):
            assert step.verify() is False


# ===========================================================================
# SympyStep
# ===========================================================================


class TestSympyStep:

    def _make(self):
        from cas_service.setup._sympy import SympyStep
        return SympyStep()

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_check_good_version(self, mock_run):
        """check() returns True for SymPy 1.13.0 (>= 1.12)."""
        mock_run.return_value = _completed(0, stdout="1.13.0\n")
        step = self._make()
        assert step.check() is True

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_check_old_version(self, mock_run):
        """check() returns False for SymPy 1.11.1 (< 1.12)."""
        mock_run.return_value = _completed(0, stdout="1.11.1\n")
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_check_exact_minimum(self, mock_run):
        """check() returns True for exactly SymPy 1.12."""
        mock_run.return_value = _completed(0, stdout="1.12\n")
        step = self._make()
        assert step.check() is True

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_check_uv_run_fails(self, mock_run):
        """check() returns False when uv run python fails."""
        mock_run.return_value = _completed(1)
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._sympy.subprocess.run", side_effect=OSError("no uv"))
    def test_check_exception(self, mock_run):
        """check() returns False on subprocess exception."""
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_check_unparseable_version(self, mock_run):
        """check() returns False for unparseable version string."""
        mock_run.return_value = _completed(0, stdout="development\n")
        step = self._make()
        assert step.check() is False

    # -- install -------------------------------------------------------------

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_install_success(self, mock_run):
        """install() runs uv sync and returns True."""
        mock_run.return_value = _completed(0)
        step = self._make()
        assert step.install(_console()) is True

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_install_fails(self, mock_run):
        """install() returns False when uv sync fails."""
        mock_run.return_value = _completed(1, stderr="resolution error")
        step = self._make()
        assert step.install(_console()) is False

    @patch("cas_service.setup._sympy.subprocess.run", side_effect=OSError("no uv"))
    def test_install_exception(self, mock_run):
        """install() returns False on subprocess exception."""
        step = self._make()
        assert step.install(_console()) is False

    # -- verify --------------------------------------------------------------

    @patch("cas_service.setup._sympy.subprocess.run")
    def test_verify_delegates_to_check_version(self, mock_run):
        """verify() returns True when _check_version passes."""
        mock_run.return_value = _completed(0, stdout="1.13.0\n")
        step = self._make()
        assert step.verify() is True


# ===========================================================================
# ServiceStep
# ===========================================================================


class TestServiceStep:

    def _make(self):
        from cas_service.setup._service import ServiceStep
        return ServiceStep()

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_check_enabled(self, mock_isfile, mock_run):
        """check() returns True when unit file exists and service is enabled."""
        mock_run.return_value = _completed(0, stdout="enabled\n")
        step = self._make()
        assert step.check() is True

    @patch("cas_service.setup._service.os.path.isfile", return_value=False)
    def test_check_no_unit_file(self, mock_isfile):
        """check() returns False when unit file does not exist."""
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_check_disabled(self, mock_isfile, mock_run):
        """check() returns False when service is disabled."""
        mock_run.return_value = _completed(0, stdout="disabled\n")
        step = self._make()
        assert step.check() is False

    @patch(
        "cas_service.setup._service.subprocess.run",
        side_effect=OSError("no systemctl"),
    )
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_check_systemctl_error(self, mock_isfile, mock_run):
        """check() returns False when systemctl command fails."""
        step = self._make()
        assert step.check() is False

    # -- install (systemd) ---------------------------------------------------

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.questionary")
    def test_install_systemd_success(
        self, mock_q, mock_isfile, mock_which, mock_run
    ):
        """install() successfully sets up systemd service."""
        mock_q.select.return_value.ask.return_value = "systemd (recommended)"
        mock_run.return_value = _completed(0)
        step = self._make()
        assert step.install(_console()) is True
        # cp + daemon-reload + enable + start = 4 subprocess calls
        assert mock_run.call_count == 4

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("cas_service.setup._service.os.path.isfile", return_value=False)
    @patch("cas_service.setup._service.questionary")
    def test_install_systemd_no_unit_source(
        self, mock_q, mock_isfile, mock_which, mock_run
    ):
        """install() returns False when source unit file is missing."""
        mock_q.select.return_value.ask.return_value = "systemd (recommended)"
        step = self._make()
        assert step.install(_console()) is False

    @patch("cas_service.setup._service.shutil.which", return_value=None)
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.questionary")
    def test_install_no_systemctl_falls_back_to_foreground(self, mock_q, mock_isfile, mock_which):
        """install() falls back to foreground when systemctl is not available."""
        step = self._make()
        assert step.install(_console()) is True
        assert step._mode == "foreground"
        mock_q.select.assert_not_called()

    @patch(
        "cas_service.setup._service.subprocess.run",
        side_effect=subprocess.CalledProcessError(
            1, "sudo", stderr="Permission denied"
        ),
    )
    @patch("cas_service.setup._service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.questionary")
    def test_install_systemd_permission_denied(
        self, mock_q, mock_isfile, mock_which, mock_run
    ):
        """install() returns False when sudo cp fails."""
        mock_q.select.return_value.ask.return_value = "systemd (recommended)"
        step = self._make()
        assert step.install(_console()) is False

    # -- install (foreground) ------------------------------------------------

    @patch("cas_service.setup._service.questionary")
    def test_install_foreground(self, mock_q):
        """install() shows foreground instructions and returns True."""
        mock_q.select.return_value.ask.return_value = "foreground"
        step = self._make()
        assert step.install(_console()) is True

    # -- verify --------------------------------------------------------------

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_verify_systemd_mode(self, mock_isfile, mock_run):
        """verify() delegates to check() in systemd mode."""
        mock_run.return_value = _completed(0, stdout="enabled\n")
        step = self._make()
        step._mode = "systemd (recommended)"
        assert step.verify() is True

    def test_verify_foreground_mode(self):
        """verify() always returns True in foreground mode."""
        step = self._make()
        step._mode = "foreground"
        assert step.verify() is True

    def test_verify_no_mode_set(self):
        """verify() returns True when mode is None (foreground fallback)."""
        step = self._make()
        assert step._mode is None
        assert step.verify() is True


# ===========================================================================
# VerifyStep
# ===========================================================================


class TestVerifyStep:

    def _make(self):
        from cas_service.setup._verify import VerifyStep
        return VerifyStep()

    # -- _get_json helper ----------------------------------------------------

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    def test_get_json_success(self, mock_urlopen):
        """_get_json returns parsed dict on success."""
        from cas_service.setup._verify import VerifyStep

        body = json.dumps({"status": "ok"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = VerifyStep._get_json("/health")
        assert result == {"status": "ok"}

    @patch(
        "cas_service.setup._verify.urllib.request.urlopen",
        side_effect=ConnectionRefusedError("Connection refused"),
    )
    def test_get_json_connection_refused(self, mock_urlopen):
        """_get_json returns None when service is unreachable."""
        from cas_service.setup._verify import VerifyStep

        result = VerifyStep._get_json("/health")
        assert result is None

    @patch("cas_service.setup._verify.urllib.request.urlopen")
    def test_get_json_invalid_json(self, mock_urlopen):
        """_get_json returns None when response is not valid JSON."""
        from cas_service.setup._verify import VerifyStep

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = VerifyStep._get_json("/health")
        assert result is None

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._verify.VerifyStep._get_json")
    def test_check_healthy(self, mock_get):
        """check() returns True when /health returns status ok."""
        mock_get.return_value = {"status": "ok"}
        step = self._make()
        assert step.check() is True

    @patch("cas_service.setup._verify.VerifyStep._get_json")
    def test_check_unhealthy(self, mock_get):
        """check() returns False when /health returns non-ok status."""
        mock_get.return_value = {"status": "error"}
        step = self._make()
        assert step.check() is False

    @patch("cas_service.setup._verify.VerifyStep._get_json", return_value=None)
    def test_check_unreachable(self, mock_get):
        """check() returns False when service is unreachable."""
        step = self._make()
        assert step.check() is False

    # -- install -------------------------------------------------------------

    @patch("cas_service.setup._verify.VerifyStep._get_json")
    def test_install_service_running(self, mock_get):
        """install() returns True and shows engine table when service is up."""
        mock_get.side_effect = [
            {"status": "ok", "uptime_seconds": 120},
            {
                "engines": [
                    {
                        "name": "sympy",
                        "available": True,
                        "description": "SymPy engine",
                    },
                    {
                        "name": "sage",
                        "available": True,
                        "description": "SageMath engine",
                    },
                    {
                        "name": "matlab",
                        "available": False,
                        "description": "MATLAB engine",
                    },
                ]
            },
        ]
        step = self._make()
        assert step.install(_console()) is True

    @patch("cas_service.setup._verify.VerifyStep._get_json", return_value=None)
    def test_install_service_unreachable(self, mock_get):
        """install() returns False when service is not running."""
        step = self._make()
        assert step.install(_console()) is False

    @patch("cas_service.setup._verify.VerifyStep._get_json")
    def test_install_health_ok_engines_unreachable(self, mock_get):
        """install() returns True even if /engines fails (secondary endpoint)."""
        mock_get.side_effect = [
            {"status": "ok", "uptime_seconds": 30},
            None,
        ]
        step = self._make()
        assert step.install(_console()) is True

    # -- verify --------------------------------------------------------------

    @patch("cas_service.setup._verify.VerifyStep._get_json")
    def test_verify_healthy(self, mock_get):
        """verify() returns True when /health returns ok."""
        mock_get.return_value = {"status": "ok"}
        step = self._make()
        assert step.verify() is True

    @patch("cas_service.setup._verify.VerifyStep._get_json", return_value=None)
    def test_verify_unreachable(self, mock_get):
        """verify() returns False when service is unreachable."""
        step = self._make()
        assert step.verify() is False


# ===========================================================================
# Runner (run_steps)
# ===========================================================================


class TestRunner:

    def _make_step(
        self,
        name: str,
        check: bool = False,
        install: bool = True,
        verify: bool = True,
    ):
        """Create a mock step with configurable behavior."""
        step = MagicMock()
        step.name = name
        step.check.return_value = check
        step.install.return_value = install
        step.verify.return_value = verify
        return step

    @patch("cas_service.setup._runner.questionary")
    def test_all_steps_already_configured(self, mock_q):
        """run_steps returns True when all checks pass (no install needed)."""
        from cas_service.setup._runner import run_steps

        steps = [
            self._make_step("Python", check=True),
            self._make_step("Maxima", check=True),
        ]
        result = run_steps(steps, _console())
        assert result is True
        for s in steps:
            s.check.assert_called_once()
            s.install.assert_not_called()

    @patch("cas_service.setup._runner.questionary")
    def test_step_install_and_verify(self, mock_q):
        """run_steps installs and verifies a step that fails check."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        step = self._make_step("SymPy", check=False, install=True, verify=True)
        result = run_steps([step], _console())
        assert result is True
        step.install.assert_called_once()
        step.verify.assert_called_once()

    @patch("cas_service.setup._runner.questionary")
    def test_user_skips_step(self, mock_q):
        """run_steps marks step as skipped when user declines."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = False
        step = self._make_step("MATLAB", check=False)
        result = run_steps([step], _console())
        assert result is True  # skipped != failed
        step.install.assert_not_called()

    @patch("cas_service.setup._runner.questionary")
    def test_install_fails_user_aborts(self, mock_q):
        """run_steps returns False when install fails and user aborts."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        mock_q.select.return_value.ask.return_value = "Abort"
        step = self._make_step("Maxima", check=False, install=False)
        result = run_steps([step], _console())
        assert result is False

    @patch("cas_service.setup._runner.questionary")
    def test_install_fails_user_skips(self, mock_q):
        """run_steps continues when install fails and user chooses skip."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        mock_q.select.return_value.ask.return_value = "Skip and continue"
        step = self._make_step("MATLAB", check=False, install=False)
        result = run_steps([step], _console())
        assert result is True  # skipped, not failed

    @patch("cas_service.setup._runner.questionary")
    def test_install_fails_retry_succeeds(self, mock_q):
        """run_steps retries and succeeds on second attempt."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        mock_q.select.return_value.ask.return_value = "Retry"
        step = self._make_step("Maxima", check=False, verify=True)
        # First install fails, retry succeeds
        step.install.side_effect = [False, True]
        result = run_steps([step], _console())
        assert result is True
        assert step.install.call_count == 2
        step.verify.assert_called_once()

    @patch("cas_service.setup._runner.questionary")
    def test_install_fails_retry_fails(self, mock_q):
        """run_steps marks step as failed after retry also fails."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        mock_q.select.return_value.ask.return_value = "Retry"
        step = self._make_step("Maxima", check=False, install=False)
        result = run_steps([step], _console())
        assert result is False  # failed step
        assert step.install.call_count == 2

    @patch("cas_service.setup._runner.questionary")
    def test_verify_fails_shows_warning(self, mock_q):
        """run_steps shows warning when verify fails after install succeeds."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        step = self._make_step("SymPy", check=False, install=True, verify=False)
        result = run_steps([step], _console())
        # "warn" is not "failed", so overall result is True
        assert result is True

    @patch("cas_service.setup._runner.questionary")
    def test_mixed_steps(self, mock_q):
        """run_steps handles a mix of passing, installed, and skipped steps."""
        from cas_service.setup._runner import run_steps

        # First step: already ok
        step1 = self._make_step("Python", check=True)
        # Second step: needs install, user confirms
        step2 = self._make_step("SymPy", check=False, install=True, verify=True)
        # Third step: needs install, user skips
        step3 = self._make_step("MATLAB", check=False)

        # confirm: True for step2, False for step3
        mock_q.confirm.return_value.ask.side_effect = [True, False]

        result = run_steps([step1, step2, step3], _console())
        assert result is True
        step1.install.assert_not_called()
        step2.install.assert_called_once()
        step3.install.assert_not_called()

    @patch("cas_service.setup._runner.questionary")
    def test_empty_steps_list(self, mock_q):
        """run_steps returns True for empty steps list."""
        from cas_service.setup._runner import run_steps

        result = run_steps([], _console())
        assert result is True


# ===========================================================================
# Main entry point
# ===========================================================================


class TestMain:

    @patch("cas_service.setup.main.run_steps", return_value=True)
    @patch("cas_service.setup.main.Console")
    def test_main_no_args_runs_all(self, mock_console_cls, mock_run_steps):
        """main() with no args runs all setup steps."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        main(args=[])
        mock_run_steps.assert_called_once()
        steps = mock_run_steps.call_args[0][0]
        assert len(steps) == 7  # Python, SymPy, MATLAB, Sage, WA, Service, Verify

    @patch("cas_service.setup.main.run_steps", return_value=True)
    @patch("cas_service.setup.main.Console")
    def test_main_engines_subcommand(self, mock_console_cls, mock_run_steps):
        """main(args=['engines']) runs engine-only steps."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        main(args=["engines"])
        mock_run_steps.assert_called_once()
        steps = mock_run_steps.call_args[0][0]
        assert len(steps) == 4  # SymPy, MATLAB, Sage, WA

    @patch("cas_service.setup.main.run_steps", return_value=True)
    @patch("cas_service.setup.main.Console")
    def test_main_verify_subcommand(self, mock_console_cls, mock_run_steps):
        """main(args=['verify']) runs verification step only."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        main(args=["verify"])
        mock_run_steps.assert_called_once()
        steps = mock_run_steps.call_args[0][0]
        assert len(steps) == 1

    @patch("cas_service.setup.main.run_steps", return_value=True)
    @patch("cas_service.setup.main.Console")
    def test_main_service_subcommand(self, mock_console_cls, mock_run_steps):
        """main(args=['service']) runs service step only."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        main(args=["service"])
        mock_run_steps.assert_called_once()
        steps = mock_run_steps.call_args[0][0]
        assert len(steps) == 1

    @patch("cas_service.setup.main.Console")
    def test_main_unknown_subcommand_exits(self, mock_console_cls):
        """main() exits with code 1 for unknown subcommand."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        with pytest.raises(SystemExit) as exc_info:
            main(args=["bogus"])
        assert exc_info.value.code == 1

    @patch("cas_service.setup.main.Console")
    def test_main_help_returns(self, mock_console_cls):
        """main(args=['--help']) prints usage and returns (no exit)."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        # Should not raise
        main(args=["--help"])

    @patch("cas_service.setup.main.run_steps", return_value=False)
    @patch("cas_service.setup.main.Console")
    def test_main_failure_exits_1(self, mock_console_cls, mock_run_steps):
        """main() exits with code 1 when run_steps returns False."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        with pytest.raises(SystemExit) as exc_info:
            main(args=[])
        assert exc_info.value.code == 1


# ===========================================================================
# _print_summary (runner internal)
# ===========================================================================


class TestPrintSummary:

    def test_print_summary_all_statuses(self):
        """_print_summary handles all status types without error."""
        from cas_service.setup._runner import _print_summary

        results = [
            ("Python", "ok"),
            ("MATLAB", "skipped"),
            ("Service", "failed"),
            ("SymPy", "warn"),
            ("Unknown", "custom"),
        ]
        # Should not raise
        _print_summary(results, _console())
