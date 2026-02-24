"""Setup step: MATLAB (optional) — searches common install paths, configures path."""

from __future__ import annotations

import glob
import os

from rich.console import Console

from cas_service.setup._config import get_key, write_key

# Common MATLAB binary locations across platforms
_SEARCH_PATHS = [
    "/usr/local/MATLAB/*/bin/matlab",
    "/Applications/MATLAB_*.app/bin/matlab",
    "/opt/MATLAB/*/bin/matlab",
    os.path.expanduser("~/MATLAB/*/bin/matlab"),
    "/media/*/matlab*/bin/matlab",
    "/media/*/*/matlab*/bin/matlab",
]


class MatlabStep:
    """Search for MATLAB binary. This engine is optional."""

    name = "MATLAB (optional)"

    def __init__(self) -> None:
        self._found_path: str | None = None

    def check(self) -> bool:
        """Return True if a MATLAB binary is configured or found."""
        configured = get_key("CAS_MATLAB_PATH")
        if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
            self._found_path = configured
            return True
        self._found_path = self._find_matlab()
        return self._found_path is not None

    def install(self, console: Console) -> bool:
        """Report MATLAB status and prompt for custom path."""
        # Try auto-detection first
        path = self._find_matlab()
        if path:
            console.print(f"  MATLAB detected at: [bold]{path}[/]")
            self._found_path = path
            write_key("CAS_MATLAB_PATH", path)
            console.print(f"  Saved CAS_MATLAB_PATH={path} to .env")
            return True

        console.print("  MATLAB is [bold]optional[/] — the CAS service works without it.")
        console.print("  Searched paths:")
        for pattern in _SEARCH_PATHS:
            console.print(f"    {pattern}")
        console.print()

        # Let user provide a custom path
        try:
            import questionary

            custom = questionary.text(
                "Enter MATLAB binary path (or press Enter to skip):",
                default="",
            ).ask()
            if custom and os.path.isfile(custom) and os.access(custom, os.X_OK):
                self._found_path = custom
                write_key("CAS_MATLAB_PATH", custom)
                console.print(f"  [green]Saved CAS_MATLAB_PATH={custom}[/]")
                return True
            if custom:
                console.print(f"  [yellow]Path not found or not executable: {custom}[/]")
        except Exception:
            pass

        console.print(
            "  [yellow]MATLAB not found — skipping (this is fine).[/]"
        )
        return False

    def verify(self) -> bool:
        """Verify the found MATLAB binary is executable."""
        if self._found_path and os.path.isfile(self._found_path):
            return os.access(self._found_path, os.X_OK)
        return False

    @staticmethod
    def _find_matlab() -> str | None:
        """Search common paths for the MATLAB binary."""
        # Check configured path first
        configured = get_key("CAS_MATLAB_PATH")
        if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        for pattern in _SEARCH_PATHS:
            if "*" in pattern:
                matches = sorted(glob.glob(pattern), reverse=True)
                for match in matches:
                    if os.path.isfile(match) and os.access(match, os.X_OK):
                        return match
            else:
                if os.path.isfile(pattern) and os.access(pattern, os.X_OK):
                    return pattern
        return None
