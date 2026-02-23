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
        """Hit /health, /engines, and optionally /compute smoke test."""
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
        table.add_column("Capabilities")
        table.add_column("Description")

        compute_engines = []
        for engine in engines:
            available = engine.get("available", False)
            capabilities = engine.get("capabilities", [])
            status_str = (
                "[green]yes[/]" if available else "[red]no[/]"
            )
            table.add_row(
                engine.get("name", "?"),
                status_str,
                ", ".join(capabilities) if capabilities else "-",
                engine.get("description", "").strip().split("\n")[0][:50],
            )
            if available and "compute" in capabilities:
                compute_engines.append(engine["name"])

        console.print(table)

        # Smoke test /compute if any compute engine is available
        if compute_engines:
            self._smoke_test_compute(console, compute_engines[0])

        return True

    def verify(self) -> bool:
        """Verify health endpoint returns ok."""
        return self._health_ok()

    @staticmethod
    def _smoke_test_compute(console: Console, engine_name: str) -> None:
        """Best-effort smoke test for /compute with a simple template."""
        console.print()
        console.print(
            f"  Smoke-testing /compute with engine '{engine_name}'..."
        )
        try:
            payload = json.dumps({
                "engine": engine_name,
                "task_type": "template",
                "template": "group_order",
                "inputs": {"group_expr": "SymmetricGroup(3)"},
                "timeout_s": 5,
            }).encode()
            req = urllib.request.Request(
                f"{SERVICE_URL}/compute",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            if data.get("success"):
                value = data.get("result", {}).get("value", "?")
                console.print(
                    f"  [green]Compute OK[/] — "
                    f"SymmetricGroup(3) order = {value}"
                )
            else:
                error = data.get("error", "unknown")
                console.print(
                    f"  [yellow]Compute returned error:[/] {error}"
                )
        except Exception as exc:
            console.print(f"  [yellow]Compute smoke test skipped:[/] {exc}")

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
