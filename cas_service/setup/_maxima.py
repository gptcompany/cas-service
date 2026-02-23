"""Setup step: Maxima CAS engine (version >= 5.44)."""

from __future__ import annotations

import re
import shutil
import subprocess

from rich.console import Console

MIN_VERSION = (5, 44)


class MaximaStep:
    """Check that Maxima is installed with version >= 5.44."""

    name = "Maxima"

    def check(self) -> bool:
        """Return True if maxima is on PATH and version >= 5.44."""
        path = shutil.which("maxima")
        if not path:
            return False
        version = self._get_version(path)
        if version is None:
            return False
        return version >= MIN_VERSION

    def install(self, console: Console) -> bool:
        """Show install instructions (cannot auto-install system packages)."""
        console.print("  Maxima is a system package. Install with your package manager:")
        console.print()
        console.print("    [bold]Ubuntu / Debian:[/]")
        console.print("      sudo apt update && sudo apt install -y maxima")
        console.print()
        console.print("    [bold]macOS (Homebrew):[/]")
        console.print("      brew install maxima")
        console.print()
        console.print("    [bold]Arch Linux:[/]")
        console.print("      sudo pacman -S maxima")
        console.print()
        console.print(
            f"  Minimum version: [bold]{MIN_VERSION[0]}.{MIN_VERSION[1]}[/]"
        )

        # Try auto-install on Ubuntu/Debian
        if shutil.which("apt-get"):
            console.print()
            console.print("  Attempting auto-install via apt...")
            try:
                result = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "maxima"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    console.print("  [green]Maxima installed via apt.[/]")
                    return True
                console.print(f"  [red]apt install failed:[/] {result.stderr[:200]}")
                return False
            except Exception as exc:
                console.print(f"  [red]Auto-install failed: {exc}[/]")
                return False

        console.print()
        console.print(
            "  [yellow]Cannot auto-install on this platform. "
            "Please install manually and re-run.[/]"
        )
        return False

    def verify(self) -> bool:
        """Verify maxima is on PATH with correct version."""
        return self.check()

    @staticmethod
    def _get_version(path: str) -> tuple[int, ...] | None:
        """Parse Maxima version string into a tuple."""
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            text = result.stdout.strip()
            # Typical output: "Maxima 5.47.0"
            match = re.search(r"(\d+)\.(\d+)", text)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except Exception:
            pass
        return None
