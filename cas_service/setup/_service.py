"""Setup step: systemd service, Docker Compose, or foreground run configuration."""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import questionary
from rich.console import Console

from pathlib import Path

from cas_service.setup._config import DEFAULT_CAS_PORT, get_cas_port, get_key, set_cas_port

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
UNIT_FILE_SRC = os.path.join(PROJECT_ROOT, "cas-service.service")
UNIT_FILE_DST = "/etc/systemd/system/cas-service.service"
COMPOSE_FILE = os.path.join(PROJECT_ROOT, "docker-compose.yml")

# Container-side MATLAB mount point (matches docker-compose.yml volumes)
_DOCKER_MATLAB_MOUNT = "/opt/matlab"


def _render_systemd_unit(template: str) -> str:
    """Render cas-service.service template with local paths and current user."""
    user = getpass.getuser()
    venv_python = Path(PROJECT_ROOT) / ".venv" / "bin" / "python"
    exec_start = f"{venv_python} -m cas_service.main"

    rendered = template.replace("User=your-username", f"User={user}")
    rendered = rendered.replace(
        "WorkingDirectory=/path/to/cas-service",
        f"WorkingDirectory={PROJECT_ROOT}",
    )
    rendered = rendered.replace(
        "ExecStart=/usr/local/bin/uv run python -m cas_service.main",
        f"ExecStart={exec_start}",
    )
    return rendered


def _enable_matlab_volume(compose_text: str, matlab_root: str) -> str:
    """Enable MATLAB volume mount in docker-compose.yml content.

    Handles two cases:
    1. Commented-out volumes section → uncomment and set path
    2. No volumes section → insert after healthcheck block
    """
    volume_line = f"      - {matlab_root}:{_DOCKER_MATLAB_MOUNT}:ro"

    # Case 1: uncomment existing commented volumes
    pattern = re.compile(
        r"^(\s*)#\s*volumes:\s*\n\s*#\s*-\s*[^\n]*matlab[^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(compose_text)
    if match:
        indent = match.group(1) or "    "
        replacement = f"{indent}volumes:\n{volume_line}"
        return compose_text[: match.start()] + replacement + compose_text[match.end() :]

    # Case 2: insert volumes after restart line
    restart_match = re.search(r"^(\s*)restart:.*$", compose_text, re.MULTILINE)
    if restart_match:
        indent = restart_match.group(1) or "    "
        insert = f"\n{indent}volumes:\n{volume_line}"
        pos = restart_match.end()
        return compose_text[:pos] + insert + compose_text[pos:]

    return compose_text


class ServiceStep:
    """Configure CAS service deployment: systemd, Docker Compose, or foreground."""

    name = "Service deployment"
    description = "Choose systemd, docker, or foreground"

    def __init__(self) -> None:
        self._mode: str | None = None  # "systemd", "docker", or "foreground"

    def check(self) -> bool:
        """Return True if a deployment is already configured."""
        # Deployment is considered configured only if it is also reachable on
        # the currently configured CAS_PORT.
        if self._is_docker_running() and self._health_ok():
            return True
        # Then systemd
        if not os.path.isfile(UNIT_FILE_DST):
            return False
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "cas-service"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() == "enabled" and self._health_ok()
        except Exception:
            return False

    def install(self, console: Console) -> bool:
        """Offer systemd, Docker Compose, or foreground deployment."""
        choices: list[str] = []

        has_systemd = bool(shutil.which("systemctl"))
        has_docker = self._has_docker_compose()

        if has_systemd:
            choices.append("systemd (recommended)")
        if has_docker:
            choices.append("docker compose")
        choices.append("foreground")

        if len(choices) == 1:
            # Only foreground available
            console.print(
                "  [dim]systemd and Docker not available — using foreground mode.[/]"
            )
            self._mode = "foreground"
            return self._show_foreground(console)

        if not self._configure_port(console):
            return False

        console.print("  Deployment options:")
        if has_systemd:
            console.print(
                "    [bold]systemd[/]  — runs as background service, auto-starts on boot"
            )
        if has_docker:
            console.print(
                "    [bold]docker[/]   — runs in container (SageMath included, MATLAB via volume)"
            )
        console.print(
            "    [bold]foreground[/] — runs in terminal (for testing / development)"
        )
        if has_docker:
            console.print(
                "  [green]Recommended default for most users: docker compose[/]"
            )
        console.print()
        default_mode = (
            "docker compose"
            if has_docker
            else ("systemd (recommended)" if has_systemd else "foreground")
        )
        self._mode = questionary.select(
            "How do you want to run the CAS service?",
            choices=choices,
            default=default_mode,
        ).ask()
        if self._mode is None:
            console.print("  [yellow]Selection cancelled.[/]")
            return False

        if self._mode and self._mode.startswith("systemd"):
            return self._install_systemd(console)
        if self._mode and self._mode.startswith("docker"):
            return self._install_docker(console)
        return self._show_foreground(console)

    @staticmethod
    def _configure_port(console: Console) -> bool:
        current = get_cas_port()
        default_choice = f"Use default port ({DEFAULT_CAS_PORT})"
        custom_choice = f"Use custom port (current: {current})"
        port_choice = questionary.select(
            "CAS service port configuration:",
            choices=[default_choice, custom_choice],
            default=custom_choice if current != DEFAULT_CAS_PORT else default_choice,
        ).ask()
        if port_choice is None:
            console.print("  [yellow]Port selection cancelled.[/]")
            return False

        if port_choice == default_choice:
            if not set_cas_port(DEFAULT_CAS_PORT):
                console.print("  [red]Failed to set default CAS_PORT.[/]")
                return False
            console.print(f"  [green]CAS_PORT set to default {DEFAULT_CAS_PORT}[/]")
            return True

        custom_raw = questionary.text(
            "Enter CAS port (1-65535):",
            default=str(current),
        ).ask()
        if custom_raw is None:
            console.print("  [yellow]Port input cancelled.[/]")
            return False
        try:
            custom_port = int(custom_raw.strip())
        except ValueError:
            console.print("  [red]Invalid port. Must be an integer 1-65535.[/]")
            return False
        if ServiceStep._port_in_use(custom_port):
            console.print(
                f"  [yellow]Port {custom_port} appears to be already in use.[/]"
            )
            if ServiceStep._looks_like_cas_on_port(custom_port):
                console.print(
                    "  [dim]Detected a CAS-like /health endpoint on that port.[/]"
                )
            if not questionary.confirm(
                f"Use port {custom_port} anyway?",
                default=False,
            ).ask():
                console.print("  [yellow]Choose another port and retry.[/]")
                return False
        if not set_cas_port(custom_port):
            console.print("  [red]Invalid port. Must be between 1 and 65535.[/]")
            return False
        console.print(f"  [green]CAS_PORT set to {custom_port}[/]")
        return True

    def verify(self) -> bool:
        """Verify the chosen deployment is configured."""
        if self._mode and self._mode.startswith("systemd"):
            return self._health_ok()
        if self._mode and self._mode.startswith("docker"):
            return self._is_docker_running() and self._health_ok()
        # Foreground mode always "verifies" — user just runs the command
        return True

    # ------------------------------------------------------------------
    # systemd
    # ------------------------------------------------------------------

    def _install_systemd(self, console: Console) -> bool:
        """Copy unit file, daemon-reload, enable the service."""
        if not os.path.isfile(UNIT_FILE_SRC):
            console.print(f"  [red]Unit file not found: {UNIT_FILE_SRC}[/]")
            return False

        if not shutil.which("systemctl"):
            console.print("  [red]systemctl not found — not a systemd system?[/]")
            console.print("  Use foreground mode instead.")
            return False

        console.print("  Rendering unit file with local user/path...")
        try:
            template = Path(UNIT_FILE_SRC).read_text()
            rendered = _render_systemd_unit(template)
            tmp = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".service",
                delete=False,
                encoding="utf-8",
            )
            try:
                tmp.write(rendered)
                tmp.flush()
            finally:
                tmp.close()

            console.print(f"  Copying rendered unit -> {UNIT_FILE_DST}")
            subprocess.run(
                ["sudo", "cp", tmp.name, UNIT_FILE_DST],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            console.print("  Running daemon-reload...")
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            console.print("  Enabling cas-service...")
            subprocess.run(
                ["sudo", "systemctl", "enable", "cas-service"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            console.print("  Starting cas-service...")
            subprocess.run(
                ["sudo", "systemctl", "start", "cas-service"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            console.print("  [green]systemd service installed and started.[/]")
            return True
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            console.print(f"  [red]systemd setup failed:[/] {stderr[:200]}")
            return False
        except Exception as exc:
            console.print(f"  [red]Error: {exc}[/]")
            return False
        finally:
            try:
                if "tmp" in locals():
                    os.unlink(tmp.name)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Docker Compose
    # ------------------------------------------------------------------

    def _install_docker(self, console: Console) -> bool:
        """Build and start the service with Docker Compose."""
        if not os.path.isfile(COMPOSE_FILE):
            console.print(f"  [red]docker-compose.yml not found: {COMPOSE_FILE}[/]")
            return False

        # Check if MATLAB is configured and offer volume mount
        self._maybe_enable_matlab_volume(console)

        console.print("  Building Docker image...")
        try:
            subprocess.run(
                ["docker", "compose", "build"],
                check=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=600,
            )
            console.print("  [green]Docker image built successfully.[/]")
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            console.print(f"  [red]Docker build failed:[/] {stderr[:300]}")
            return False

        # Start with dotenvx if available (decrypts .env), otherwise plain
        env_file = os.path.join(PROJECT_ROOT, ".env")
        has_dotenvx = bool(shutil.which("dotenvx"))
        has_env = os.path.isfile(env_file)

        if has_dotenvx and has_env:
            console.print("  Starting with dotenvx (decrypted .env)...")
            cmd = [
                "dotenvx",
                "run",
                "-f",
                env_file,
                "--",
                "docker",
                "compose",
                "up",
                "-d",
            ]
        else:
            if has_env and not has_dotenvx:
                console.print(
                    "  [yellow]dotenvx not found — .env won't be decrypted "
                    "automatically.[/]"
                )
                console.print("  [dim]Install dotenvx or pass env vars manually.[/]")
            console.print("  Starting container...")
            cmd = ["docker", "compose", "up", "-d"]

        run_env = os.environ.copy()
        run_env["CAS_PORT"] = str(get_cas_port())

        try:
            subprocess.run(
                cmd,
                check=True,
                text=True,
                cwd=PROJECT_ROOT,
                env=run_env,
                timeout=60,
            )
            console.print("  [green]Docker container started.[/]")
            if not self._wait_health(timeout_s=45):
                console.print(
                    f"  [red]CAS /health is not reachable on configured port {get_cas_port()} after startup.[/]"
                )
                try:
                    logs = subprocess.run(
                        ["docker", "compose", "logs", "--tail", "80"],
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                        timeout=20,
                    )
                    if logs.returncode == 0 and logs.stdout.strip():
                        console.print("  [yellow]Recent container logs:[/]")
                        console.print(logs.stdout[-2000:])
                except Exception:
                    pass
                return False
            console.print()
            console.print("  Useful commands:")
            console.print(f"    [bold]cd {PROJECT_ROOT}[/]")
            console.print("    docker compose logs -f    # view logs")
            console.print("    docker compose down       # stop")
            console.print(
                "    dotenvx run -f .env -- docker compose up -d  # restart with secrets"
            )
            console.print()
            return True
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            console.print(f"  [red]Docker start failed:[/] {stderr[:300]}")
            return False

    @staticmethod
    def _health_ok() -> bool:
        port = get_cas_port()
        url = f"http://localhost:{port}/health"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
        except (urllib.error.URLError, OSError, json.JSONDecodeError, Exception):
            return False

    def _wait_health(self, timeout_s: int = 45) -> bool:
        start = time.time()
        while time.time() - start < timeout_s:
            if self._health_ok():
                return True
            time.sleep(2)
        return False

    # ------------------------------------------------------------------
    # Foreground
    # ------------------------------------------------------------------

    @staticmethod
    def _show_foreground(console: Console) -> bool:
        """Show the foreground run command."""
        console.print()
        console.print("  To run the CAS service in the foreground:")
        console.print()
        console.print(
            f"    [bold]cd {PROJECT_ROOT} && uv run python -m cas_service.main[/]"
        )
        console.print()
        console.print("  Environment variables (optional):")
        console.print(f"    CAS_PORT={DEFAULT_CAS_PORT}")
        console.print("    CAS_SAGE_PATH=sage")
        console.print(
            "    CAS_WOLFRAMALPHA_APPID=<your-appid>  # optional remote engine"
        )
        console.print("    CAS_LOG_LEVEL=INFO")
        console.print()
        return True

    # ------------------------------------------------------------------
    # Docker MATLAB volume
    # ------------------------------------------------------------------

    @staticmethod
    def _maybe_enable_matlab_volume(console: Console) -> None:
        """If MATLAB is configured on host, offer to enable Docker volume mount."""
        matlab_path = get_key("CAS_MATLAB_PATH")
        if not matlab_path:
            return

        # Resolve the MATLAB root (e.g. /media/sam/3TB-WDC/matlab2025 from .../bin/matlab)
        resolved = (
            shutil.which(matlab_path) if not os.path.isabs(matlab_path) else matlab_path
        )
        if not resolved or not os.path.isfile(resolved):
            return

        matlab_root = str(Path(resolved).resolve().parent.parent)
        if not os.path.isdir(matlab_root):
            return

        console.print(f"  [cyan]MATLAB detected on host:[/] {matlab_root}")
        console.print("  Docker containers cannot access host paths directly.")
        enable = questionary.confirm(
            f"  Mount {matlab_root} into container at {_DOCKER_MATLAB_MOUNT}?",
            default=True,
        ).ask()
        if not enable:
            console.print(
                "  [yellow]Skipping MATLAB mount — MATLAB won't be available in Docker.[/]"
            )
            return

        # Enable volume mount in docker-compose.yml
        compose_text = Path(COMPOSE_FILE).read_text()
        container_matlab_bin = f"{_DOCKER_MATLAB_MOUNT}/bin/matlab"

        if f"{matlab_root}:{_DOCKER_MATLAB_MOUNT}" in compose_text:
            console.print("  [dim]MATLAB volume already configured.[/]")
        else:
            # Replace commented volume section or add new one
            updated = _enable_matlab_volume(compose_text, matlab_root)
            if updated != compose_text:
                Path(COMPOSE_FILE).write_text(updated)
                console.print(
                    f"  [green]Enabled volume:[/] {matlab_root} -> {_DOCKER_MATLAB_MOUNT}"
                )
            else:
                console.print("  [yellow]Could not auto-edit docker-compose.yml.[/]")
                console.print(
                    f"  Add manually under services.cas-service:\n"
                    f"    volumes:\n"
                    f"      - {matlab_root}:{_DOCKER_MATLAB_MOUNT}:ro"
                )

        # Update CAS_MATLAB_PATH to container-side path
        from cas_service.setup._config import write_key

        write_key("CAS_MATLAB_PATH", container_matlab_bin)
        console.print(
            f"  [green]Set CAS_MATLAB_PATH={container_matlab_bin}[/] (container path)"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_docker_compose() -> bool:
        """Check if docker and docker compose (v2 plugin) are available."""
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return False
            except OSError:
                return True

    @staticmethod
    def _looks_like_cas_on_port(port: int) -> bool:
        try:
            req = urllib.request.Request(
                f"http://localhost:{port}/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
            service = str(data.get("service", "")).lower()
            return data.get("status") == "ok" and "cas" in service
        except Exception:
            return False

    @staticmethod
    def _is_docker_running() -> bool:
        """Check if the cas-service container is running."""
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "-q", "cas-service"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=10,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except Exception:
            return False
