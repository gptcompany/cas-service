"""Setup step: MATLAB (optional) — searches common install paths."""

from __future__ import annotations

import glob
import os

from rich.console import Console

# Common MATLAB binary locations across platforms
_SEARCH_PATHS = [
    "/usr/local/MATLAB/*/bin/matlab",
    "/Applications/MATLAB_*.app/bin/matlab",
    "/opt/MATLAB/*/bin/matlab",
    os.path.expanduser("~/MATLAB/*/bin/matlab"),
]


class MatlabStep:
    """Search for MATLAB binary. This engine is optional."""

    name = "MATLAB (optional)"

    def __init__(self) -> None:
        self._found_path: str | None = None

    def check(self) -> bool:
        """Return True if a MATLAB binary is found in any search path."""
        self._found_path = self._find_matlab()
        return self._found_path is not None

    def install(self, console: Console) -> bool:
        """Report MATLAB status — cannot auto-install a commercial product."""
        console.print("  MATLAB is [bold]optional[/] — the CAS service works without it.")
        console.print("  SymPy and Maxima handle most validation needs.")
        console.print()
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
                console.print(f"  [green]Found MATLAB at: {custom}[/]")
                console.print(
                    f"  Set CAS_MATLAB_PATH={custom} in your environment "
                    "or cas-service.service"
                )
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
