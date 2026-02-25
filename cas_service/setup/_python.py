"""Setup step: Python >= 3.10, uv availability, uv sync."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


class PythonStep:
    """Verify Python >= 3.10, uv installed, and dependencies synced."""

    name = "Python + uv"
    description = "Python >= 3.10, uv, project dependencies"

    def check(self) -> bool:
        """Return True if Python >= 3.10, uv exists, and venv is synced."""
        if sys.version_info < (3, 10):
            return False
        if not shutil.which("uv"):
            return False
        # Check that venv exists and uv sync has been run
        try:
            result = subprocess.run(
                ["uv", "sync", "--dry-run"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=PROJECT_ROOT,
            )
            # If dry-run shows nothing to install, we're good
            return result.returncode == 0 and "install" not in result.stderr.lower()
        except Exception:
            return False

    def install(self, console: Console) -> bool:
        """Run uv sync to install project dependencies."""
        if sys.version_info < (3, 10):
            console.print(
                f"  [red]Python {sys.version_info.major}.{sys.version_info.minor} "
                f"detected — need >= 3.10[/]"
            )
            console.print("  Install Python 3.11+ via your package manager:")
            console.print("    Ubuntu:  sudo apt install python3.11")
            console.print("    macOS:   brew install python@3.11")
            console.print("    Arch:    sudo pacman -S python")
            return False

        if not shutil.which("uv"):
            console.print("  [yellow]uv not found — installing...[/]")
            try:
                subprocess.run(
                    ["pip", "install", "uv"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
            except Exception as exc:
                console.print(f"  [red]Failed to install uv: {exc}[/]")
                console.print("  Install manually: pip install uv")
                console.print("  Or: curl -LsSf https://astral.sh/uv/install.sh | sh")
                return False

        console.print("  Running [bold]uv sync[/] ...")
        try:
            result = subprocess.run(
                ["uv", "sync"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=PROJECT_ROOT,
            )
            if result.returncode != 0:
                console.print(f"  [red]uv sync failed:[/]\n{result.stderr}")
                return False
            console.print("  Dependencies synced.")
            return True
        except Exception as exc:
            console.print(f"  [red]uv sync error: {exc}[/]")
            return False

    def verify(self) -> bool:
        """Verify Python version and uv are functional."""
        if sys.version_info < (3, 10):
            return False
        if not shutil.which("uv"):
            return False
        try:
            result = subprocess.run(
                ["uv", "run", "python", "-c", "import sys; print(sys.version)"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=PROJECT_ROOT,
            )
            return result.returncode == 0
        except Exception:
            return False
