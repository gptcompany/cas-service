"""Setup step: Maxima CAS engine (version >= 5.44) — detect, install, configure."""

from __future__ import annotations

import re
import shutil
import subprocess

from rich.console import Console

from cas_service.setup._config import get_key, write_key

MIN_VERSION = (5, 44)


class MaximaStep:
    """Check that Maxima is installed with version >= 5.44."""

    name = "Maxima"

    def __init__(self) -> None:
        self._found_path: str | None = None

    def check(self) -> bool:
        """Return True if maxima is on PATH or configured with correct version."""
        configured = get_key("CAS_MAXIMA_PATH")
        if configured and shutil.which(configured):
            version = self._get_version(configured)
            if version and version >= MIN_VERSION:
                self._found_path = configured
                return True
        path = shutil.which("maxima")
        if path:
            version = self._get_version(path)
            if version and version >= MIN_VERSION:
                self._found_path = path
                return True
        return False

    def install(self, console: Console) -> bool:
        """Interactive Maxima setup."""
        path = shutil.which("maxima")
        if path:
            version = self._get_version(path)
            if version and version >= MIN_VERSION:
                console.print(
                    f"  Maxima detected at: [bold]{path}[/]"
                    f"  (v{version[0]}.{version[1]})"
                )
                self._found_path = path
                write_key("CAS_MAXIMA_PATH", path)
                console.print(f"  Saved CAS_MAXIMA_PATH={path} to .env")
                return True
            if version:
                console.print(
                    f"  Maxima found (v{version[0]}.{version[1]}) but "
                    f"minimum required is v{MIN_VERSION[0]}.{MIN_VERSION[1]}"
                )

        # Auto-install on Debian/Ubuntu
        if shutil.which("apt-get"):
            console.print("  Attempting auto-install via apt...")
            try:
                result = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "maxima"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    path = shutil.which("maxima")
                    if path:
                        self._found_path = path
                        write_key("CAS_MAXIMA_PATH", path)
                        console.print(f"  [green]Maxima installed at {path}[/]")
                        return True
                console.print(f"  [red]apt install failed:[/] {result.stderr[:200]}")
            except Exception as exc:
                console.print(f"  [red]Auto-install failed: {exc}[/]")

        # Prompt for custom path
        try:
            import questionary

            custom = questionary.text(
                "Enter maxima binary path (or press Enter to skip):",
                default="",
            ).ask()
            if custom and shutil.which(custom):
                version = self._get_version(custom)
                if version and version >= MIN_VERSION:
                    self._found_path = custom
                    write_key("CAS_MAXIMA_PATH", custom)
                    console.print(f"  [green]Saved CAS_MAXIMA_PATH={custom}[/]")
                    return True
                console.print(f"  [yellow]Version too old or not found: {custom}[/]")
            elif custom:
                console.print(f"  [yellow]Not found or not executable: {custom}[/]")
        except Exception:
            pass

        console.print("  [yellow]Maxima not configured.[/]")
        console.print(
            f"  Install version >= {MIN_VERSION[0]}.{MIN_VERSION[1]} and re-run."
        )
        return False

    def verify(self) -> bool:
        """Verify maxima is on PATH with correct version."""
        if self._found_path:
            version = self._get_version(self._found_path)
            return version is not None and version >= MIN_VERSION
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
            match = re.search(r"(\d+)\.(\d+)", text)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except Exception:
            pass
        return None
