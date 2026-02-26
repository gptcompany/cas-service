"""Extra tests for ServiceStep (Docker and edge cases)."""

from __future__ import annotations

import os
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


class TestServiceStepExtra:
    def _make(self):
        from cas_service.setup._service import ServiceStep

        return ServiceStep()

    # -- Docker Install ------------------------------------------------------

    @patch("cas_service.setup._service.shutil.which")
    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_install_docker_success(self, mock_isfile, mock_run, mock_which):
        """_install_docker builds and runs container."""
        # mock_which for docker, docker compose version, and dotenvx
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        mock_run.return_value = _completed(0)
        
        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"):
            assert step._install_docker(_console()) is True
        
        # 1. docker compose build
        # 2. docker compose up -d (via dotenvx if found)
        assert mock_run.call_count == 2
        args0 = mock_run.call_args_list[0][0][0]
        assert "build" in args0
        args1 = mock_run.call_args_list[1][0][0]
        assert "up" in args1

    @patch("cas_service.setup._service.shutil.which", return_value=None)
    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_install_docker_no_dotenvx(self, mock_isfile, mock_run, mock_which):
        """_install_docker works without dotenvx."""
        mock_which.side_effect = lambda x: "/usr/bin/docker" if x == "docker" else None
        mock_run.return_value = _completed(0)
        
        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"):
            assert step._install_docker(_console()) is True
        
        args1 = mock_run.call_args_list[1][0][0]
        assert args1[0] == "docker"

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_install_docker_build_fails(self, mock_isfile, mock_run):
        """_install_docker returns False if build fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker")
        
        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"):
            assert step._install_docker(_console()) is False

    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_install_docker_up_fails(self, mock_isfile, mock_run):
        """_install_docker returns False if up fails."""
        mock_run.side_effect = [
            _completed(0), # build ok
            subprocess.CalledProcessError(1, "docker") # up fail
        ]
        
        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"):
            assert step._install_docker(_console()) is False

    # -- Systemd edge cases --------------------------------------------------

    @patch("cas_service.setup._service.subprocess.run", side_effect=Exception("Unexpected crash"))
    @patch("cas_service.setup._service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_install_systemd_exception(self, mock_isfile, mock_which, mock_run):
        """_install_systemd handles unexpected exceptions."""
        step = self._make()
        assert step._install_systemd(_console()) is False

    # -- MATLAB volume extra logic -------------------------------------------

    @patch("cas_service.setup._service.questionary")
    @patch("cas_service.setup._service.Path")
    @patch("cas_service.setup._service.os.path.isdir", return_value=True)
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.shutil.which", side_effect=lambda x: f"/usr/bin/{x}" if x == "matlab" else x)
    @patch("cas_service.setup._service.get_key", return_value="matlab")
    def test_maybe_enable_matlab_volume_relative_path(self, mock_key, mock_which, mock_isfile, mock_isdir, mock_path, mock_q):
        """_maybe_enable_matlab_volume resolves relative MATLAB path via shutil.which."""
        mock_q.confirm.return_value.ask.return_value = True
        
        mock_path_inst = MagicMock()
        mock_path_inst.resolve.return_value.parent.parent = MagicMock()
        mock_path_inst.resolve.return_value.parent.parent.__str__.return_value = "/opt/MATLAB/R2024b"
        mock_path_inst.read_text.return_value = "restart: unless-stopped"
        mock_path.return_value = mock_path_inst
        
        from cas_service.setup._service import ServiceStep
        with patch("cas_service.setup._config.write_key"):
            ServiceStep._maybe_enable_matlab_volume(_console())
            # Should write updated docker-compose.yml
            mock_path_inst.write_text.assert_called_once()

    @patch("cas_service.setup._service.questionary")
    @patch("cas_service.setup._service.Path")
    @patch("cas_service.setup._service.os.path.isdir", return_value=True)
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.get_key", return_value="/opt/matlab/bin/matlab")
    def test_maybe_enable_matlab_volume_already_present(self, mock_key, mock_isfile, mock_isdir, mock_path, mock_q):
        """_maybe_enable_matlab_volume does not rewrite if volume already in compose file."""
        mock_q.confirm.return_value.ask.return_value = True
        
        mock_path_inst = MagicMock()
        mock_path_inst.resolve.return_value.parent.parent.__str__.return_value = "/opt/matlab"
        mock_path_inst.read_text.return_value = "volumes:\n      - /opt/matlab:/opt/matlab:ro"
        mock_path.return_value = mock_path_inst
        
        from cas_service.setup._service import ServiceStep
        with patch("cas_service.setup._config.write_key"):
            ServiceStep._maybe_enable_matlab_volume(_console())
            mock_path_inst.write_text.assert_not_called()

    # -- verify docker -------------------------------------------------------

    def test_verify_docker_mode(self):
        """verify() calls _is_docker_running in docker mode."""
        step = self._make()
        step._mode = "docker compose"
        with patch("cas_service.setup._service.ServiceStep._is_docker_running", return_value=True):
            assert step.verify() is True
        with patch("cas_service.setup._service.ServiceStep._is_docker_running", return_value=False):
            assert step.verify() is False
