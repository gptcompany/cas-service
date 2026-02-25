"""Tests for CAS Service setup wizard -- steps, runner, and main entry point."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
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
    @patch(
        "cas_service.setup._matlab.glob.glob",
        return_value=["/usr/local/MATLAB/R2025a/bin/matlab"],
    )
    def test_check_found_direct_path(self, mock_glob, mock_isfile, mock_access):
        """check() returns True when MATLAB found at a standard path."""
        step = self._make()
        assert step.check() is True
        assert step._found_path is not None

    @patch("cas_service.setup._matlab.shutil.which", return_value="/usr/bin/matlab")
    @patch("cas_service.setup._matlab.get_key", return_value="matlab")
    def test_check_with_configured_command_name(self, mock_get_key, mock_which):
        """check() accepts CAS_MATLAB_PATH as command name when on PATH."""
        step = self._make()
        assert step.check() is True
        assert step._found_path == "/usr/bin/matlab"

    @patch("cas_service.setup._matlab.shutil.which", return_value="/usr/bin/matlab")
    @patch("cas_service.setup._matlab.get_key", return_value=None)
    def test_check_found_on_path(self, mock_get_key, mock_which):
        """check() detects MATLAB from PATH even when no config is set."""
        step = self._make()
        assert step.check() is True
        assert step._found_path == "/usr/bin/matlab"

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
        with (
            patch.dict("sys.modules", {"questionary": mock_questionary}),
            patch(
                "cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None
            ),
            patch("cas_service.setup._matlab.os.path.isfile", return_value=True),
            patch("cas_service.setup._matlab.os.access", return_value=True),
        ):
            assert step.install(_console()) is True
            assert step._found_path == "/opt/matlab/bin/matlab"

    def test_install_custom_command_name_valid(self):
        """install() accepts a MATLAB command name available on PATH."""
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = "matlab"
        step = self._make()
        with (
            patch.dict("sys.modules", {"questionary": mock_questionary}),
            patch(
                "cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None
            ),
            patch(
                "cas_service.setup._matlab.shutil.which", return_value="/usr/bin/matlab"
            ),
        ):
            assert step.install(_console()) is True
            assert step._found_path == "/usr/bin/matlab"

    def test_install_custom_path_invalid(self):
        """install() returns False for invalid custom path."""
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = "/nope/matlab"
        step = self._make()
        with (
            patch.dict("sys.modules", {"questionary": mock_questionary}),
            patch(
                "cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None
            ),
            patch("cas_service.setup._matlab.os.path.isfile", return_value=False),
        ):
            assert step.install(_console()) is False

    def test_install_user_skips(self):
        """install() returns False when user presses Enter (empty path)."""
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = ""
        step = self._make()
        with (
            patch.dict("sys.modules", {"questionary": mock_questionary}),
            patch(
                "cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None
            ),
        ):
            assert step.install(_console()) is False

    def test_install_questionary_unavailable(self):
        """install() returns False gracefully when questionary is not installed."""
        step = self._make()
        # Simulate questionary not being importable inside install()
        with (
            patch.dict("sys.modules", {"questionary": None}),
            patch(
                "cas_service.setup._matlab.MatlabStep._find_matlab", return_value=None
            ),
        ):
            # When module is None in sys.modules, import raises ImportError
            assert step.install(_console()) is False

    # -- verify --------------------------------------------------------------

    def test_verify_with_found_path(self):
        """verify() returns True when _found_path is set and executable."""
        step = self._make()
        step._found_path = "/opt/matlab/bin/matlab"
        with (
            patch("cas_service.setup._matlab.os.path.isfile", return_value=True),
            patch("cas_service.setup._matlab.os.access", return_value=True),
        ):
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
        with (
            patch("cas_service.setup._matlab.os.path.isfile", return_value=True),
            patch("cas_service.setup._matlab.os.access", return_value=False),
        ):
            assert step.verify() is False

    @patch("cas_service.setup._matlab.shutil.which", return_value="/usr/bin/matlab")
    def test_verify_command_name_on_path(self, mock_which):
        """verify() accepts command names, not only absolute paths."""
        step = self._make()
        step._found_path = "matlab"
        assert step.verify() is True


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
# SageStep
# ===========================================================================


class TestSageStep:
    def _make(self):
        from cas_service.setup._sage import SageStep

        return SageStep()

    @patch("cas_service.setup._sage.os.access")
    @patch("cas_service.setup._sage.os.path.isfile")
    @patch(
        "cas_service.setup._sage.glob.glob",
        return_value=["/media/sam/3TB-WDC/apps/sage/sage"],
    )
    @patch("cas_service.setup._sage.shutil.which", side_effect=[None, None])
    @patch("cas_service.setup._sage.get_key", return_value=None)
    def test_find_sage_via_media_glob(
        self,
        mock_get_key,
        mock_which,
        mock_glob,
        mock_isfile,
        mock_access,
    ):
        """_find_sage() supports external-drive layouts under /media/.../apps."""
        mock_isfile.side_effect = lambda p: p == "/media/sam/3TB-WDC/apps/sage/sage"
        mock_access.side_effect = (
            lambda p, mode: p == "/media/sam/3TB-WDC/apps/sage/sage"
        )
        step = self._make()
        assert step._find_sage() == "/media/sam/3TB-WDC/apps/sage/sage"


# ===========================================================================
# ServiceStep
# ===========================================================================


class TestServiceStep:
    def _make(self):
        from cas_service.setup._service import ServiceStep

        return ServiceStep()

    # -- check ---------------------------------------------------------------

    @patch(
        "cas_service.setup._service.ServiceStep._is_docker_running", return_value=False
    )
    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_check_enabled(self, mock_isfile, mock_run, _mock_docker):
        """check() returns True when unit file exists and service is enabled."""
        mock_run.return_value = _completed(0, stdout="enabled\n")
        step = self._make()
        assert step.check() is True

    @patch("cas_service.setup._service.os.path.isfile", return_value=False)
    def test_check_no_unit_file(self, mock_isfile):
        """check() returns False when unit file does not exist."""
        step = self._make()
        assert step.check() is False

    @patch(
        "cas_service.setup._service.ServiceStep._is_docker_running", return_value=False
    )
    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_check_disabled(self, mock_isfile, mock_run, _mock_docker):
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

    @patch(
        "cas_service.setup._service.ServiceStep._has_docker_compose", return_value=False
    )
    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.questionary")
    def test_install_systemd_success(
        self, mock_q, mock_isfile, mock_which, mock_run, _mock_docker
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
    def test_install_no_systemctl_falls_back_to_foreground(
        self, mock_q, mock_isfile, mock_which
    ):
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

    @patch("cas_service.setup._service.questionary")
    def test_install_selection_cancelled(self, mock_q):
        """install() returns False when user cancels mode selection."""
        mock_q.select.return_value.ask.return_value = None
        step = self._make()
        assert step.install(_console()) is False

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
# Docker MATLAB volume mount
# ===========================================================================


class TestEnableMatlabVolume:
    """Tests for _enable_matlab_volume helper."""

    def _call(self, compose_text, matlab_root):
        from cas_service.setup._service import _enable_matlab_volume

        return _enable_matlab_volume(compose_text, matlab_root)

    def test_uncomments_existing_volume(self):
        """Uncomments the commented-out MATLAB volume section."""
        compose = (
            "services:\n"
            "  cas-service:\n"
            "    restart: unless-stopped\n"
            "    # Per MATLAB: decommentare e impostare il path host\n"
            "    # volumes:\n"
            "    #   - /usr/local/MATLAB:/opt/matlab:ro\n"
        )
        result = self._call(compose, "/media/sam/3TB-WDC/matlab2025")
        assert "volumes:" in result
        assert "/media/sam/3TB-WDC/matlab2025:/opt/matlab:ro" in result
        assert "#" not in result.split("volumes:")[1].split("\n")[0]

    def test_inserts_after_restart_if_no_volumes(self):
        """Adds volumes section after restart line if none exists."""
        compose = "services:\n  cas-service:\n    restart: unless-stopped\n"
        result = self._call(compose, "/opt/MATLAB/R2025b")
        assert "volumes:" in result
        assert "/opt/MATLAB/R2025b:/opt/matlab:ro" in result

    def test_returns_unchanged_if_no_anchor(self):
        """Returns text unchanged if no restart line found."""
        compose = "services:\n  cas-service:\n    build: .\n"
        result = self._call(compose, "/opt/MATLAB")
        assert result == compose


class TestMaybeEnableMatlabVolume:
    """Tests for ServiceStep._maybe_enable_matlab_volume."""

    @patch("cas_service.setup._service.get_key", return_value=None)
    def test_noop_when_no_matlab_configured(self, mock_key):
        """Does nothing if CAS_MATLAB_PATH not set."""
        from cas_service.setup._service import ServiceStep

        ServiceStep._maybe_enable_matlab_volume(_console())
        # No error, no crash

    @patch("cas_service.setup._service.questionary")
    @patch("cas_service.setup._service.Path")
    @patch("cas_service.setup._service.os.path.isdir", return_value=True)
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.os.path.isabs", return_value=True)
    @patch(
        "cas_service.setup._service.get_key",
        return_value="/media/sam/3TB-WDC/matlab2025/bin/matlab",
    )
    def test_skips_when_user_declines(
        self, mock_key, mock_isabs, mock_isfile, mock_isdir, mock_path, mock_q
    ):
        """Skips volume mount when user declines."""
        mock_q.confirm.return_value.ask.return_value = False
        mock_path_inst = MagicMock()
        mock_path_inst.resolve.return_value.parent.parent = Path(
            "/media/sam/3TB-WDC/matlab2025"
        )
        mock_path.return_value = mock_path_inst

        from cas_service.setup._service import ServiceStep

        ServiceStep._maybe_enable_matlab_volume(_console())
        # No file written


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
        step.description = f"{name} step"
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
    def test_user_cancels_confirm_aborts(self, mock_q):
        """run_steps returns False when user cancels the confirm prompt."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = None
        step = self._make_step("MATLAB", check=False)
        result = run_steps([step], _console())
        assert result is False
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
    def test_install_fails_prompt_cancel_aborts(self, mock_q):
        """run_steps returns False when retry/skip/abort prompt is cancelled."""
        from cas_service.setup._runner import run_steps

        mock_q.confirm.return_value.ask.return_value = True
        mock_q.select.return_value.ask.return_value = None
        step = self._make_step("MATLAB", check=False, install=False)
        result = run_steps([step], _console())
        assert result is False

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

    @patch("cas_service.setup._runner.questionary")
    def test_interactive_menu_exit_all_ok(self, mock_q):
        """run_interactive_menu returns True when user exits and all steps are OK."""
        from cas_service.setup._runner import run_interactive_menu

        mock_q.select.return_value.ask.return_value = "exit"
        steps = [
            self._make_step("Python", check=True),
            self._make_step("SymPy", check=True),
        ]
        result = run_interactive_menu(steps, _console())
        assert result is True
        for step in steps:
            assert step.check.call_count == 1

    @patch("cas_service.setup._runner._run_single_step", return_value="ok")
    @patch("cas_service.setup._runner.questionary")
    def test_interactive_menu_run_all_pending(self, mock_q, mock_run_one):
        """run_interactive_menu runs only pending steps for 'Run all pending'."""
        from cas_service.setup._runner import run_interactive_menu

        mock_q.select.return_value.ask.side_effect = ["run_all", "exit"]
        step_ok = self._make_step("Python", check=True)
        step_pending = self._make_step("Sage")
        step_pending.check.side_effect = [False, True, True]

        result = run_interactive_menu([step_ok, step_pending], _console())

        assert result is True
        mock_run_one.assert_called_once()
        assert mock_run_one.call_args[0][0] is step_pending

    @patch("cas_service.setup._runner._run_single_step", return_value="skipped")
    @patch("cas_service.setup._runner.questionary")
    def test_interactive_menu_preserves_skipped_status(self, mock_q, mock_run_one):
        """Skipping an optional step in menu should not force exit code 1."""
        from cas_service.setup._runner import run_interactive_menu

        mock_q.select.return_value.ask.side_effect = [0, "exit"]
        step = self._make_step("MATLAB")
        step.check.side_effect = [False, False, False]

        result = run_interactive_menu([step], _console())

        assert result is True
        mock_run_one.assert_called_once()

    @patch("cas_service.setup._runner._run_single_step", return_value="ok")
    @patch("cas_service.setup._runner.questionary")
    def test_interactive_menu_refreshes_only_invalidated_steps(
        self, mock_q, mock_run_one
    ):
        """Menu uses cached statuses and refreshes after invalidation only."""
        from cas_service.setup._runner import run_interactive_menu

        mock_q.select.return_value.ask.side_effect = [0, "exit"]
        step1 = self._make_step("Python")
        step2 = self._make_step("SymPy")
        # Initial snapshot: both pending. After running step1, refresh from step1 onward: both ok.
        step1.check.side_effect = [False, True]
        step2.check.side_effect = [False, True]

        result = run_interactive_menu([step1, step2], _console())

        assert result is True
        mock_run_one.assert_called_once()
        assert step1.check.call_count == 2
        assert step2.check.call_count == 2


# ===========================================================================
# Main entry point
# ===========================================================================


class TestMain:
    @patch("cas_service.setup.main.run_steps", return_value=True)
    @patch("cas_service.setup.main.run_interactive_menu", return_value=True)
    @patch("cas_service.setup.main.Console")
    def test_main_no_args_runs_all(
        self, mock_console_cls, mock_run_menu, mock_run_steps
    ):
        """main() with no args runs interactive menu with all setup steps."""
        from cas_service.setup.main import main

        mock_console_cls.return_value = _console()
        main(args=[])
        mock_run_menu.assert_called_once()
        mock_run_steps.assert_not_called()
        steps = mock_run_menu.call_args[0][0]
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

    @patch("cas_service.setup.main.run_interactive_menu", return_value=False)
    @patch("cas_service.setup.main.Console")
    def test_main_failure_exits_1(self, mock_console_cls, mock_run_menu):
        """main() exits with code 1 when interactive menu returns False."""
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
