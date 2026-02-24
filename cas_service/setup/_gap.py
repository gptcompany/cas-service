"""Setup step: GAP computational algebra system — detect, install, configure."""

from __future__ import annotations

import os
import shutil
import subprocess

from rich.console import Console

from cas_service.setup._config import get_key, write_key


class GapStep:
    """Check that GAP is installed and accessible."""

    name = "GAP"

    def __init__(self) -> None:
        self._found_path: str | None = None

    def check(self) -> bool:
        """Return True if gap is on PATH or configured and responds."""
        configured = get_key("CAS_GAP_PATH")
        if configured and shutil.which(configured):
            if self._get_version(configured):
                self._found_path = configured
                return True
        path = shutil.which("gap")
        if path and self._get_version(path):
            self._found_path = path
            return True
        return False

    def install(self, console: Console) -> bool:
        """Interactive GAP setup."""
        path = shutil.which("gap")
        if path:
            version = self._get_version(path)
            console.print(f"  GAP detected at: [bold]{path}[/]")
            if version:
                console.print(f"  Version: {version}")
            self._found_path = path
            write_key("CAS_GAP_PATH", path)
            console.print(f"  Saved CAS_GAP_PATH={path} to .env")
            return True

        # Auto-install on Debian/Ubuntu
        if shutil.which("apt-get"):
            console.print("  GAP not found. Attempting auto-install via apt...")
            try:
                result = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "gap"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    path = shutil.which("gap")
                    if path:
                        self._found_path = path
                        write_key("CAS_GAP_PATH", path)
                        console.print(f"  [green]GAP installed at {path}[/]")
                        return True
                console.print(f"  [red]apt install failed:[/] {result.stderr[:200]}")
            except Exception as exc:
                console.print(f"  [red]Auto-install failed: {exc}[/]")

        # Prompt for custom path
        try:
            import questionary

            custom = questionary.text(
                "Enter GAP binary path (or press Enter to skip):",
                default="",
            ).ask()
            if custom and shutil.which(custom):
                self._found_path = custom
                write_key("CAS_GAP_PATH", custom)
                console.print(f"  [green]Saved CAS_GAP_PATH={custom}[/]")
                return True
            if custom:
                console.print(f"  [yellow]Not found or not executable: {custom}[/]")
        except Exception:
            pass

        console.print("  [yellow]GAP not configured.[/]")
        console.print("  Install: https://www.gap-system.org/Releases/")
        console.print("  Set CAS_GAP_PATH when ready.")
        return False

    def verify(self) -> bool:
        """Verify GAP binary is functional."""
        if not self._found_path:
            return self.check()
        return self._get_version(self._found_path) is not None

    @staticmethod
    def _get_version(path: str) -> str | None:
        """Query GAP version."""
        try:
            result = subprocess.run(
                [path, "-q", "-b"],
                input='Print(GAPInfo.Version);;\n',
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None
