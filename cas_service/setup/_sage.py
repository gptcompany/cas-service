"""Setup step: SageMath — detect, auto-install, configure path."""

from __future__ import annotations

import shutil
import subprocess

from rich.console import Console

from cas_service.setup._config import get_key, write_key

# Common SageMath binary locations
_SEARCH_PATHS = [
    "/usr/bin/sage",
    "/usr/local/bin/sage",
    "/opt/sage/sage",
]


class SageStep:
    """Detect, install, and configure SageMath."""

    name = "SageMath"

    def __init__(self) -> None:
        self._found_path: str | None = None

    def check(self) -> bool:
        """Return True if sage is on PATH or configured."""
        configured = get_key("CAS_SAGE_PATH")
        if configured and shutil.which(configured):
            self._found_path = configured
            return True
        path = shutil.which("sage")
        if path:
            self._found_path = path
            return True
        return False

    def install(self, console: Console) -> bool:
        """Interactive SageMath setup: detect, install, or prompt for path."""
        # Try existing paths first
        path = self._find_sage()
        if path:
            version = self._get_version(path)
            console.print(f"  SageMath detected at: [bold]{path}[/]")
            if version:
                console.print(f"  Version: {version}")
            self._found_path = path
            write_key("CAS_SAGE_PATH", path)
            console.print(f"  Saved CAS_SAGE_PATH={path} to .env")
            return True

        # Offer auto-install on Debian/Ubuntu
        if shutil.which("apt-get"):
            console.print("  SageMath not found. Attempting auto-install via apt...")
            console.print("  [dim](This may take a few minutes — ~2GB download)[/]")
            try:
                result = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "sagemath"],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode == 0:
                    path = shutil.which("sage")
                    if path:
                        self._found_path = path
                        write_key("CAS_SAGE_PATH", path)
                        console.print(f"  [green]SageMath installed at {path}[/]")
                        return True
                console.print(
                    f"  [red]apt install failed:[/] {result.stderr[:200]}"
                )
            except Exception as exc:
                console.print(f"  [red]Auto-install failed: {exc}[/]")

        # Prompt for custom path
        try:
            import questionary

            custom = questionary.text(
                "Enter sage binary path (or press Enter to skip):",
                default="",
            ).ask()
            if custom and shutil.which(custom):
                self._found_path = custom
                write_key("CAS_SAGE_PATH", custom)
                console.print(f"  [green]Saved CAS_SAGE_PATH={custom}[/]")
                return True
            if custom:
                console.print(f"  [yellow]Not found or not executable: {custom}[/]")
        except Exception:
            pass

        console.print("  [yellow]SageMath not configured — skipping.[/]")
        console.print("  Install: https://doc.sagemath.org/html/en/installation/")
        console.print("  Set CAS_SAGE_PATH when ready.")
        return False

    def verify(self) -> bool:
        """Verify sage binary is functional."""
        if not self._found_path:
            return False
        try:
            result = subprocess.run(
                [self._found_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _find_sage(self) -> str | None:
        """Search common paths for sage binary."""
        # Check config first
        configured = get_key("CAS_SAGE_PATH")
        if configured and shutil.which(configured):
            return configured
        # Check PATH
        path = shutil.which("sage")
        if path:
            return path
        # Check common locations
        import os
        for p in _SEARCH_PATHS:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        return None

    @staticmethod
    def _get_version(path: str) -> str | None:
        """Query SageMath version."""
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
