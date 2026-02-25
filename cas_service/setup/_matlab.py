"""Setup step: MATLAB (optional) — searches common install paths, configures path."""

from __future__ import annotations

import glob
import os
import shutil

from rich.console import Console

from cas_service.setup._config import env_path, get_key, write_key

# Common MATLAB binary locations across platforms
_SEARCH_PATHS = [
    "/usr/local/MATLAB/*/bin/matlab",
    "/Applications/MATLAB_*.app/bin/matlab",
    "/opt/MATLAB/*/bin/matlab",
    os.path.expanduser("~/MATLAB/*/bin/matlab"),
    "/media/*/matlab*/bin/matlab",
    "/media/*/*/matlab*/bin/matlab",
    "/media/*/apps/matlab*/bin/matlab",
    "/media/*/*/apps/matlab*/bin/matlab",
    "/media/*/MATLAB/*/bin/matlab",
    "/media/*/*/MATLAB/*/bin/matlab",
    "/Volumes/*/MATLAB*/bin/matlab",
]


class MatlabStep:
    """Search for MATLAB binary. This engine is optional."""

    name = "MATLAB (optional)"

    def __init__(self) -> None:
        self._found_path: str | None = None

    def check(self) -> bool:
        """Return True if a MATLAB binary is configured or found."""
        configured = get_key("CAS_MATLAB_PATH")
        configured_path = self._resolve_executable(configured)
        if configured_path:
            self._found_path = configured_path
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

        console.print(
            "  MATLAB is [bold]optional[/] — the CAS service works without it."
        )
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
            resolved = self._resolve_executable(custom)
            if custom and resolved:
                self._found_path = resolved
                write_key("CAS_MATLAB_PATH", resolved)
                console.print(f"  [green]Saved CAS_MATLAB_PATH={resolved}[/]")
                return True
            if custom:
                console.print(
                    f"  [yellow]Path not found or not executable: {custom}[/]"
                )
        except Exception:
            pass

        console.print("  [yellow]MATLAB not found — skipping (this is fine).[/]")
        console.print(f"  To add later, set CAS_MATLAB_PATH in: [bold]{env_path()}[/]")
        return False

    def verify(self) -> bool:
        """Verify the found MATLAB binary is executable."""
        return self._resolve_executable(self._found_path) is not None

    @staticmethod
    def _find_matlab() -> str | None:
        """Search common paths for the MATLAB binary."""
        # Check configured path first
        configured = MatlabStep._resolve_executable(get_key("CAS_MATLAB_PATH"))
        if configured:
            return configured
        # Check PATH (important when CAS_MATLAB_PATH is unset and binary is symlinked)
        in_path = shutil.which("matlab")
        if in_path:
            return in_path
        for pattern in _SEARCH_PATHS:
            if "*" in pattern:
                matches = sorted(glob.glob(pattern), reverse=True)
                for match in matches:
                    resolved = MatlabStep._resolve_executable(match)
                    if resolved:
                        return resolved
            else:
                resolved = MatlabStep._resolve_executable(pattern)
                if resolved:
                    return resolved
        return None

    @staticmethod
    def _resolve_executable(candidate: str | None) -> str | None:
        """Resolve a MATLAB executable from absolute path or command name."""
        if not candidate:
            return None
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        return shutil.which(candidate)
