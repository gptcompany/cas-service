"""Setup step: verify CAS service health and engine status."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from rich.console import Console
from rich.table import Table

SERVICE_URL = "http://localhost:8769"


class VerifyStep:
    """Check the running CAS service health and engine availability."""

    name = "Service verification"

    def check(self) -> bool:
        """Return True if /health returns status ok."""
        return self._health_ok()

    def install(self, console: Console) -> bool:
        """Hit /health and /engines, display results."""
        console.print(f"  Checking {SERVICE_URL}/health ...")
        health = self._get_json("/health")
        if health is None:
            console.print(
                f"  [red]Cannot reach {SERVICE_URL}[/] — "
                "is the service running?"
            )
            console.print()
            console.print("  Start it with:")
            console.print(
                "    uv run python -m cas_service.main"
            )
            console.print("  Or:")
            console.print("    sudo systemctl start cas-service")
            return False

        status = health.get("status", "unknown")
        uptime = health.get("uptime_seconds", "?")
        console.print(f"  Health: [green]{status}[/]  Uptime: {uptime}s")

        console.print(f"  Checking {SERVICE_URL}/engines ...")
        engines_data = self._get_json("/engines")
        if engines_data is None:
            console.print("  [yellow]Could not fetch /engines[/]")
            return True  # health passed, engines endpoint is secondary

        engines = engines_data.get("engines", [])
        table = Table(title="Engine Status", show_lines=False)
        table.add_column("Engine", style="bold")
        table.add_column("Available")
        table.add_column("Description")

        for engine in engines:
            available = engine.get("available", False)
            status_str = (
                "[green]yes[/]" if available else "[red]no[/]"
            )
            table.add_row(
                engine.get("name", "?"),
                status_str,
                engine.get("description", "").strip().split("\n")[0][:60],
            )

        console.print(table)
        return True

    def verify(self) -> bool:
        """Verify health endpoint returns ok."""
        return self._health_ok()

    @staticmethod
    def _health_ok() -> bool:
        """Quick check on /health."""
        data = VerifyStep._get_json("/health")
        return data is not None and data.get("status") == "ok"

    @staticmethod
    def _get_json(path: str) -> dict | None:
        """GET a JSON endpoint, return parsed dict or None."""
        try:
            req = urllib.request.Request(
                f"{SERVICE_URL}{path}",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, json.JSONDecodeError, Exception):
            return None
