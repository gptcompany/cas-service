"""Extra tests for ServiceStep (Docker and edge cases)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    @patch("cas_service.setup._service.get_docker_port", return_value=9011)
    def test_install_docker_success(
        self, mock_port, mock_isfile, mock_run, mock_which
    ):
        """_install_docker builds and runs container with aligned Docker env."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        mock_run.return_value = _completed(0)

        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"), patch(
            "cas_service.setup._service.ServiceStep._wait_health", return_value=True
        ):
            assert step._install_docker(_console()) is True

        assert mock_run.call_count == 2
        args0 = mock_run.call_args_list[0][0][0]
        assert "build" in args0
        args1 = mock_run.call_args_list[1][0][0]
        assert "up" in args1
        run_env = mock_run.call_args_list[1].kwargs["env"]
        assert run_env["CAS_PORT"] == "9011"
        assert run_env["CAS_DOCKER_PORT"] == "9011"

    @patch("cas_service.setup._service.shutil.which", return_value=None)
    @patch("cas_service.setup._service.subprocess.run")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.get_docker_port", return_value=8769)
    def test_install_docker_no_dotenvx(
        self, mock_port, mock_isfile, mock_run, mock_which
    ):
        """_install_docker works without dotenvx."""
        mock_which.side_effect = lambda x: "/usr/bin/docker" if x == "docker" else None
        mock_run.return_value = _completed(0)

        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"), patch(
            "cas_service.setup._service.ServiceStep._wait_health", return_value=True
        ):
            assert step._install_docker(_console()) is True

        args1 = mock_run.call_args_list[1][0][0]
        assert args1[0] == "docker"
        run_env = mock_run.call_args_list[1].kwargs["env"]
        assert run_env["CAS_PORT"] == "8769"
        assert run_env["CAS_DOCKER_PORT"] == "8769"

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
            _completed(0),
            subprocess.CalledProcessError(1, "docker"),
        ]

        step = self._make()
        with patch("cas_service.setup._service.ServiceStep._maybe_enable_matlab_volume"), patch(
            "cas_service.setup._service.ServiceStep._wait_health", return_value=True
        ):
            assert step._install_docker(_console()) is False

    # -- Systemd edge cases --------------------------------------------------

    @patch(
        "cas_service.setup._service.subprocess.run",
        side_effect=Exception("Unexpected crash"),
    )
    @patch("cas_service.setup._service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    def test_install_systemd_exception(self, mock_isfile, mock_which, mock_run):
        """_install_systemd handles unexpected exceptions."""
        step = self._make()
        assert step._install_systemd(_console()) is False

    # -- MATLAB volume extra logic -------------------------------------------

    @patch("cas_service.setup._service.questionary")
    @patch("cas_service.setup._service.write_key")
    @patch("cas_service.setup._service.os.path.isdir", return_value=True)
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch(
        "cas_service.setup._service.shutil.which",
        side_effect=lambda x: "/tmp/matlab/bin/matlab" if x == "matlab" else x,
    )
    @patch("cas_service.setup._service.get_key")
    def test_maybe_enable_matlab_volume_relative_path_writes_docker_env(
        self, mock_get_key, mock_which, mock_isfile, mock_isdir, mock_write_key, mock_q
    ):
        """_maybe_enable_matlab_volume resolves relative host MATLAB and writes Docker env keys."""
        mock_q.confirm.return_value.ask.return_value = True

        values = {
            "CAS_MATLAB_PATH": "matlab",
            "CAS_DOCKER_MATLAB_HOST_PATH": None,
            "CAS_DOCKER_MATLAB_PATH": None,
        }
        mock_get_key.side_effect = values.get

        from cas_service.setup._service import ServiceStep

        with patch("cas_service.setup._service.Path.resolve") as mock_resolve:
            mock_resolve.return_value = Path("/tmp/matlab/bin/matlab")
            ServiceStep._maybe_enable_matlab_volume(_console())

        mock_write_key.assert_any_call("CAS_DOCKER_MATLAB_HOST_PATH", "/tmp/matlab")
        mock_write_key.assert_any_call(
            "CAS_DOCKER_MATLAB_PATH", "/opt/matlab/bin/matlab"
        )

    @patch("cas_service.setup._service.questionary")
    @patch("cas_service.setup._service.write_key")
    @patch("cas_service.setup._service.os.path.isdir", return_value=True)
    @patch("cas_service.setup._service.os.path.isfile", return_value=True)
    @patch("cas_service.setup._service.get_key")
    def test_maybe_enable_matlab_volume_already_present_in_env(
        self, mock_get_key, mock_isfile, mock_isdir, mock_write_key, mock_q
    ):
        """_maybe_enable_matlab_volume does not rewrite when Docker env is already aligned."""
        values = {
            "CAS_MATLAB_PATH": "/opt/matlab/bin/matlab",
            "CAS_DOCKER_MATLAB_HOST_PATH": "/opt/matlab",
            "CAS_DOCKER_MATLAB_PATH": "/opt/matlab/bin/matlab",
        }
        mock_get_key.side_effect = values.get

        from cas_service.setup._service import ServiceStep

        with patch("cas_service.setup._service.Path.resolve") as mock_resolve:
            mock_resolve.return_value = Path("/opt/matlab/bin/matlab")
            ServiceStep._maybe_enable_matlab_volume(_console())

        mock_q.confirm.assert_not_called()
        mock_write_key.assert_not_called()

    # -- verify docker -------------------------------------------------------

    def test_verify_docker_mode(self):
        """verify() requires both docker running and /health OK in docker mode."""
        step = self._make()
        step._mode = "docker compose"
        with patch("cas_service.setup._service.ServiceStep._is_docker_running", return_value=True), patch(
            "cas_service.setup._service.ServiceStep._health_ok", return_value=True
        ):
            assert step.verify() is True
        with patch("cas_service.setup._service.ServiceStep._is_docker_running", return_value=False), patch(
            "cas_service.setup._service.ServiceStep._health_ok", return_value=True
        ):
            assert step.verify() is False


class TestSystemdTemplateRendering:
    def test_render_systemd_unit_replaces_placeholders(self):
        from cas_service.setup._service import PROJECT_ROOT, _render_systemd_unit

        template = (
            "User=your-username\n"
            "WorkingDirectory=/path/to/cas-service\n"
            "ExecStart=/usr/local/bin/uv run python -m cas_service.main\n"
        )
        with patch("cas_service.setup._service.getpass.getuser", return_value="sam"):
            rendered = _render_systemd_unit(template)

        assert "User=sam" in rendered
        assert f"WorkingDirectory={PROJECT_ROOT}" in rendered
        assert (
            f"ExecStart={PROJECT_ROOT}/.venv/bin/python -m cas_service.main"
            in rendered
        )
