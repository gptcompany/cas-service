"""Setup step: SageMath detection (info-only for this milestone)."""

from __future__ import annotations

import shutil
import subprocess

from rich.console import Console


class SageStep:
    """Detect SageMath availability — info-only, no full engine yet."""

    name = "SageMath (detection)"

    def check(self) -> bool:
        """Return True if sage is on PATH."""
        return shutil.which("sage") is not None

    def install(self, console: Console) -> bool:
        """Show SageMath status and future plans."""
        path = shutil.which("sage")
        if path:
            version = self._get_version(path)
            console.print(f"  SageMath detected at: {path}")
            if version:
                console.print(f"  Version: {version}")
            console.print(
                "  [dim]SageMath engine integration is planned for a future release.[/]"
            )
            return True

        console.print("  SageMath is not currently installed.")
        console.print()
        console.print("    [bold]Install (optional):[/]")
        console.print("      https://doc.sagemath.org/html/en/installation/")
        console.print()
        console.print(
            "  [dim]SageMath engine integration is planned for a future release.[/]"
        )
        console.print("  Set CAS_SAGE_PATH when ready.")
        return True  # Always passes — info-only step

    def verify(self) -> bool:
        """Info-only step always passes."""
        return True

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
