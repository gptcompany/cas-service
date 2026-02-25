"""Setup step: systemd service, Docker Compose, or foreground run configuration."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import questionary
from rich.console import Console

from pathlib import Path

from cas_service.setup._config import DEFAULT_CAS_PORT, get_key

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
UNIT_FILE_SRC = os.path.join(PROJECT_ROOT, "cas-service.service")
UNIT_FILE_DST = "/etc/systemd/system/cas-service.service"
COMPOSE_FILE = os.path.join(PROJECT_ROOT, "docker-compose.yml")

# Container-side MATLAB mount point (matches docker-compose.yml volumes)
_DOCKER_MATLAB_MOUNT = "/opt/matlab"


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

    def __init__(self) -> None:
        self._mode: str | None = None  # "systemd", "docker", or "foreground"

    def check(self) -> bool:
        """Return True if a deployment is already configured."""
        # Check Docker first
        if self._is_docker_running():
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
            return result.stdout.strip() == "enabled"
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

        self._mode = questionary.select(
            "How do you want to run the CAS service?",
            choices=choices,
        ).ask()
        if self._mode is None:
            console.print("  [yellow]Selection cancelled.[/]")
            return False

        if self._mode and self._mode.startswith("systemd"):
            return self._install_systemd(console)
        if self._mode and self._mode.startswith("docker"):
            return self._install_docker(console)
        return self._show_foreground(console)

    def verify(self) -> bool:
        """Verify the chosen deployment is configured."""
        if self._mode and self._mode.startswith("systemd"):
            return self.check()
        if self._mode and self._mode.startswith("docker"):
            return self._is_docker_running()
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

        console.print(f"  Copying {UNIT_FILE_SRC} -> {UNIT_FILE_DST}")
        try:
            subprocess.run(
                ["sudo", "cp", UNIT_FILE_SRC, UNIT_FILE_DST],
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
                capture_output=True,
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

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=60,
            )
            console.print("  [green]Docker container started.[/]")
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
