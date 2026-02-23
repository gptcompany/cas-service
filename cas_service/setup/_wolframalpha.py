"""Setup step: WolframAlpha API detection (env-based)."""

from __future__ import annotations

import os

from rich.console import Console


class WolframAlphaStep:
    """Detect WolframAlpha API key availability — env-only check."""

    name = "WolframAlpha (detection)"

    def check(self) -> bool:
        """Return True if CAS_WOLFRAMALPHA_APPID is set."""
        return bool(os.environ.get("CAS_WOLFRAMALPHA_APPID"))

    def install(self, console: Console) -> bool:
        """Show WolframAlpha configuration status."""
        app_id = os.environ.get("CAS_WOLFRAMALPHA_APPID")
        if app_id:
            console.print("  WolframAlpha API key detected (CAS_WOLFRAMALPHA_APPID).")
            console.print(
                "  [dim]WolframAlpha engine will be available as optional remote backend.[/]"
            )
            return True

        console.print("  WolframAlpha API key not configured.")
        console.print()
        console.print("  To enable (optional):")
        console.print("    1. Get an AppID at https://developer.wolframalpha.com/")
        console.print("    2. Set CAS_WOLFRAMALPHA_APPID in your environment")
        console.print()
        console.print(
            "  [dim]WolframAlpha is optional — the service works without it.[/]"
        )
        return True  # Always passes — optional engine

    def verify(self) -> bool:
        """Optional step always passes."""
        return True
