"""Setup step: GAP computational algebra system."""

from __future__ import annotations

import re
import shutil
import subprocess

from rich.console import Console


class GapStep:
    """Check that GAP is installed and accessible."""

    name = "GAP"

    def check(self) -> bool:
        """Return True if gap is on PATH and responds to version query."""
        path = shutil.which("gap")
        if not path:
            return False
        return self._get_version(path) is not None

    def install(self, console: Console) -> bool:
        """Show install instructions for GAP."""
        console.print("  GAP is a system for computational algebra.")
        console.print()
        console.print("    [bold]Ubuntu / Debian:[/]")
        console.print("      sudo apt update && sudo apt install -y gap")
        console.print()
        console.print("    [bold]macOS (Homebrew):[/]")
        console.print("      brew install gap")
        console.print()
        console.print("    [bold]From source:[/]")
        console.print("      https://www.gap-system.org/Releases/")
        console.print()
        console.print("  Set CAS_GAP_PATH if installed to a custom location.")

        # Try auto-install on Ubuntu/Debian
        if shutil.which("apt-get"):
            console.print()
            console.print("  Attempting auto-install via apt...")
            try:
                result = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "gap"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    console.print("  [green]GAP installed via apt.[/]")
                    return True
                console.print(
                    f"  [red]apt install failed:[/] {result.stderr[:200]}"
                )
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
        """Verify gap is on PATH and responds."""
        return self.check()

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
