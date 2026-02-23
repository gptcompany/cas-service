"""Setup step: SymPy >= 1.12 importable in venv."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
MIN_VERSION = (1, 12)


class SympyStep:
    """Verify SymPy is importable in the project venv with version >= 1.12."""

    name = "SymPy"

    def check(self) -> bool:
        """Return True if SymPy can be imported with sufficient version."""
        return self._check_version()

    def install(self, console: Console) -> bool:
        """Run uv sync to ensure SymPy is installed in the venv."""
        console.print("  Running [bold]uv sync[/] to install SymPy...")
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
            console.print("  SymPy installed via uv sync.")
            return True
        except Exception as exc:
            console.print(f"  [red]Install error: {exc}[/]")
            return False

    def verify(self) -> bool:
        """Verify SymPy importable with correct version after install."""
        return self._check_version()

    @staticmethod
    def _check_version() -> bool:
        """Check SymPy version via the project venv."""
        try:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    "-c",
                    "import sympy; print(sympy.__version__)",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=PROJECT_ROOT,
            )
            if result.returncode != 0:
                return False
            version_str = result.stdout.strip()
            parts = version_str.split(".")
            if len(parts) >= 2:
                major, minor = int(parts[0]), int(parts[1])
                return (major, minor) >= MIN_VERSION
            return False
        except Exception:
            return False
