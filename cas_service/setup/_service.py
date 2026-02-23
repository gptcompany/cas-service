"""Setup step: systemd service or foreground run configuration."""

from __future__ import annotations

import os
import shutil
import subprocess

import questionary
from rich.console import Console

PROJECT_ROOT = "/media/sam/1TB/cas-service"
UNIT_FILE_SRC = os.path.join(PROJECT_ROOT, "cas-service.service")
UNIT_FILE_DST = "/etc/systemd/system/cas-service.service"


class ServiceStep:
    """Configure CAS service deployment: systemd unit or foreground mode."""

    name = "Service deployment"

    def __init__(self) -> None:
        self._mode: str | None = None  # "systemd" or "foreground"

    def check(self) -> bool:
        """Return True if the systemd unit is already installed and enabled."""
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
        """Offer systemd or foreground deployment."""
        self._mode = questionary.select(
            "How do you want to run the CAS service?",
            choices=["systemd (recommended)", "foreground"],
        ).ask()

        if self._mode and self._mode.startswith("systemd"):
            return self._install_systemd(console)
        return self._show_foreground(console)

    def verify(self) -> bool:
        """Verify the chosen deployment is configured."""
        if self._mode and self._mode.startswith("systemd"):
            return self.check()
        # Foreground mode always "verifies" — user just runs the command
        return True

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
        console.print("    CAS_PORT=8769")
        console.print("    CAS_MAXIMA_PATH=/usr/bin/maxima")
        console.print("    CAS_LOG_LEVEL=INFO")
        console.print()
        return True
