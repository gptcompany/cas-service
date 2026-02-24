"""Setup step: WolframAlpha API key configuration (secure input)."""

from __future__ import annotations

import os

from rich.console import Console

from cas_service.setup._config import get_key, write_key


class WolframAlphaStep:
    """Configure WolframAlpha API key — optional engine."""

    name = "WolframAlpha (optional)"

    def check(self) -> bool:
        """Return True if CAS_WOLFRAMALPHA_APPID is configured."""
        return bool(get_key("CAS_WOLFRAMALPHA_APPID"))

    def install(self, console: Console) -> bool:
        """Interactive API key setup with secure (no-echo) input."""
        existing = get_key("CAS_WOLFRAMALPHA_APPID")
        if existing:
            masked = existing[:4] + "..." + existing[-4:] if len(existing) > 8 else "****"
            console.print(f"  WolframAlpha AppID already configured: {masked}")
            console.print("  [dim]Enter a new key to replace, or press Enter to keep.[/]")

        try:
            import questionary

            new_key = questionary.password(
                "WolframAlpha AppID (Enter to skip):"
            ).ask()
            if new_key and new_key.strip():
                write_key("CAS_WOLFRAMALPHA_APPID", new_key.strip())
                console.print("  [green]Saved CAS_WOLFRAMALPHA_APPID to .env[/]")
                return True
            if existing:
                console.print("  Keeping existing key.")
                return True
        except Exception:
            pass

        console.print("  WolframAlpha is [bold]optional[/] — the service works without it.")
        console.print("  To enable:")
        console.print("    1. Get an AppID at https://developer.wolframalpha.com/")
        console.print("    2. Re-run: cas-setup configure")
        return True  # Optional — always passes

    def verify(self) -> bool:
        """Optional step always passes."""
        return True
