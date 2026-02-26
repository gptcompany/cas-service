"""Tests for SageMath setup step."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console


def _console() -> Console:
    return Console(file=MagicMock(), highlight=False)


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestSageStep:
    def _make(self):
        from cas_service.setup._sage import SageStep

        return SageStep()

    # -- check ---------------------------------------------------------------

    @patch("cas_service.setup._sage.get_key", return_value="/opt/sage/sage")
    @patch("cas_service.setup._sage.shutil.which", return_value="/opt/sage/sage")
    def test_check_configured_and_exists(self, mock_which, mock_get_key):
        """check() returns True if CAS_SAGE_PATH is set and exists."""
        step = self._make()
        assert step.check() is True
        assert step._found_path == "/opt/sage/sage"

    @patch("cas_service.setup._sage.get_key", return_value=None)
    @patch("cas_service.setup._sage.shutil.which", return_value="/usr/bin/sage")
    def test_check_on_path(self, mock_which, mock_get_key):
        """check() returns True if sage is in PATH."""
        step = self._make()
        assert step.check() is True
        assert step._found_path == "/usr/bin/sage"

    @patch("cas_service.setup._sage.get_key", return_value=None)
    @patch("cas_service.setup._sage.shutil.which", return_value=None)
    def test_check_not_found(self, mock_which, mock_get_key):
        """check() returns False if not configured and not in PATH."""
        step = self._make()
        assert step.check() is False

    # -- install -------------------------------------------------------------

    @patch("cas_service.setup._sage.write_key")
    @patch("cas_service.setup._sage.SageStep._find_sage", return_value="/usr/local/bin/sage")
    @patch("cas_service.setup._sage.SageStep._get_version", return_value="SageMath 10.4")
    def test_install_detected(self, mock_version, mock_find, mock_write_key):
        """install() saves path if Sage is auto-detected."""
        step = self._make()
        assert step.install(_console()) is True
        assert step._found_path == "/usr/local/bin/sage"
        mock_write_key.assert_called_once_with("CAS_SAGE_PATH", "/usr/local/bin/sage")

    @patch("cas_service.setup._sage.subprocess.run")
    @patch("cas_service.setup._sage.shutil.which")
    @patch("cas_service.setup._sage.SageStep._find_sage", return_value=None)
    def test_install_apt_success(self, mock_find, mock_which, mock_run):
        """install() attempts apt install on Linux if sage missing."""
        mock_which.side_effect = lambda x: "/usr/bin/apt-get" if x == "apt-get" else ("/usr/bin/sage" if x == "sage" else None)
        mock_run.return_value = _completed(0)
        
        step = self._make()
        assert step.install(_console()) is True
        assert step._found_path == "/usr/bin/sage"

    @patch("cas_service.setup._sage.subprocess.run")
    @patch("cas_service.setup._sage.shutil.which")
    @patch("cas_service.setup._sage.SageStep._find_sage", return_value=None)
    def test_install_brew_success(self, mock_find, mock_which, mock_run):
        """install() attempts brew install on macOS if sage missing."""
        mock_which.side_effect = lambda x: "/usr/local/bin/brew" if x == "brew" else (None if x == "apt-get" else ("/usr/local/bin/sage" if x == "sage" else None))
        mock_run.return_value = _completed(0)
        
        step = self._make()
        assert step.install(_console()) is True
        assert step._found_path == "/usr/local/bin/sage"

    @patch("cas_service.setup._sage.subprocess.run", side_effect=Exception("apt crash"))
    @patch("cas_service.setup._sage.shutil.which")
    @patch("cas_service.setup._sage.SageStep._find_sage", return_value=None)
    def test_install_apt_fails_and_prompt(self, mock_find, mock_which, mock_run):
        """install() prompts for path if auto-install fails."""
        mock_which.side_effect = lambda x: "/usr/bin/apt-get" if x == "apt-get" else None
        
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = "/manual/sage"
        
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            with patch("cas_service.setup._sage.shutil.which", return_value="/manual/sage"):
                assert step.install(_console()) is True
                assert step._found_path == "/manual/sage"

    @patch("cas_service.setup._sage.shutil.which", return_value=None)
    @patch("cas_service.setup._sage.SageStep._find_sage", return_value=None)
    def test_install_skip_prompt(self, mock_find, mock_which):
        """install() returns False if user skips manual prompt."""
        mock_q = MagicMock()
        mock_q.text.return_value.ask.return_value = ""
        
        step = self._make()
        with patch.dict("sys.modules", {"questionary": mock_q}):
            assert step.install(_console()) is False

    # -- verify --------------------------------------------------------------

    @patch("cas_service.setup._sage.subprocess.run")
    def test_verify_success(self, mock_run):
        """verify() returns True if sage --version succeeds."""
        mock_run.return_value = _completed(0)
        step = self._make()
        step._found_path = "/usr/bin/sage"
        assert step.verify() is True

    @patch("cas_service.setup._sage.subprocess.run", side_effect=Exception("fail"))
    def test_verify_fails(self, mock_run):
        """verify() returns False on error."""
        step = self._make()
        step._found_path = "/usr/bin/sage"
        assert step.verify() is False

    def test_verify_no_path(self):
        """verify() returns False if no path set."""
        step = self._make()
        assert step.verify() is False

    # -- _find_sage ----------------------------------------------------------

    @patch("cas_service.setup._sage.get_key", return_value="/custom/sage")
    @patch("cas_service.setup._sage.shutil.which", return_value="/custom/sage")
    def test_find_sage_configured(self, mock_which, mock_get_key):
        step = self._make()
        assert step._find_sage() == "/custom/sage"

    @patch("cas_service.setup._sage.os.path.isfile", return_value=True)
    @patch("cas_service.setup._sage.os.access", return_value=True)
    @patch("cas_service.setup._sage.glob.glob")
    @patch("cas_service.setup._sage.shutil.which", return_value=None)
    @patch("cas_service.setup._sage.get_key", return_value=None)
    def test_find_sage_glob(self, mock_get_key, mock_which, mock_glob, mock_access, mock_isfile):
        mock_glob.side_effect = lambda p: [p.replace("*", "9.5")] if "*" in p else []
        step = self._make()
        # It should eventually hit one of the patterns in _SEARCH_PATHS
        path = step._find_sage()
        assert path is not None

    # -- _get_version --------------------------------------------------------

    @patch("cas_service.setup._sage.subprocess.run")
    def test_get_version_success(self, mock_run):
        mock_run.return_value = _completed(0, stdout="SageMath version 10.4, Release Date: 2024-07-20\n")
        step = self._make()
        assert step._get_version("/usr/bin/sage") == "SageMath version 10.4, Release Date: 2024-07-20"

    @patch("cas_service.setup._sage.subprocess.run", side_effect=Exception)
    def test_get_version_error(self, mock_run):
        step = self._make()
        assert step._get_version("/usr/bin/sage") is None
