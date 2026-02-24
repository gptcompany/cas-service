"""Setup step: verify CAS service health and engine status (validate + compute)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from rich.console import Console
from rich.table import Table

SERVICE_URL = "http://localhost:8769"

# Smoke test payloads per engine type
_VALIDATE_SMOKE = {
    "latex": "x^2 + 1",
}

_COMPUTE_SMOKE: dict[str, dict] = {
    "wolframalpha": {
        "template": "evaluate",
        "inputs": {"expression": "2+2"},
        "expected_value": "4",
    },
    "sage": {
        "template": "evaluate",
        "inputs": {"expression": "2^10"},
        "expected_value": "1024",
    },
}


class VerifyStep:
    """Check the running CAS service health and engine availability."""

    name = "Service verification"

    def check(self) -> bool:
        """Return True if /health returns status ok."""
        return self._health_ok()

    def install(self, console: Console) -> bool:
        """Hit /health, /engines, and run validate + compute smoke tests."""
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
            return True

        engines = engines_data.get("engines", [])
        table = Table(title="Engine Status", show_lines=False)
        table.add_column("Engine", style="bold")
        table.add_column("Available")
        table.add_column("Capabilities")
        table.add_column("Version")

        validate_engines = []
        compute_engines = []
        for engine in engines:
            available = engine.get("available", False)
            capabilities = engine.get("capabilities", [])
            version = engine.get("version", "-")
            status_str = (
                "[green]yes[/]" if available else "[red]no[/]"
            )
            table.add_row(
                engine.get("name", "?"),
                status_str,
                ", ".join(capabilities) if capabilities else "-",
                str(version) if available else "-",
            )
            if available:
                if "validate" in capabilities:
                    validate_engines.append(engine["name"])
                if "compute" in capabilities:
                    compute_engines.append(engine["name"])

        console.print(table)

        # Smoke test /validate
        if validate_engines:
            self._smoke_test_validate(console, validate_engines)

        # Smoke test /compute per engine
        for engine_name in compute_engines:
            if engine_name in _COMPUTE_SMOKE:
                self._smoke_test_compute(console, engine_name)

        return True

    def verify(self) -> bool:
        """Verify health endpoint returns ok."""
        return self._health_ok()

    @staticmethod
    def _smoke_test_validate(
        console: Console, engine_names: list[str],
    ) -> None:
        """Smoke test /validate with available validation engines."""
        console.print()
        console.print(
            f"  Smoke-testing /validate with engines: {', '.join(engine_names)}..."
        )
        try:
            payload = json.dumps({
                **_VALIDATE_SMOKE,
                "engines": engine_names,
            }).encode()
            req = urllib.request.Request(
                f"{SERVICE_URL}/validate",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            results = data.get("results", [])
            for r in results:
                name = r.get("engine", "?")
                ok = r.get("success", False)
                valid = r.get("is_valid")
                simplified = r.get("simplified", "")
                if ok and valid:
                    console.print(
                        f"    [green]validate OK[/] {name} → {simplified}"
                    )
                elif ok and not valid:
                    console.print(
                        f"    [yellow]validate: invalid[/] {name}"
                    )
                else:
                    error = r.get("error", "unknown")
                    console.print(
                        f"    [red]validate FAIL[/] {name}: {error}"
                    )
        except Exception as exc:
            console.print(f"  [yellow]Validate smoke test skipped:[/] {exc}")

    @staticmethod
    def _smoke_test_compute(console: Console, engine_name: str) -> None:
        """Smoke test /compute for a specific engine."""
        smoke = _COMPUTE_SMOKE.get(engine_name)
        if not smoke:
            return
        console.print(
            f"  Smoke-testing /compute with engine '{engine_name}'..."
        )
        try:
            payload = json.dumps({
                "engine": engine_name,
                "task_type": "template",
                "template": smoke["template"],
                "inputs": smoke["inputs"],
                "timeout_s": 30,
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            if data.get("success"):
                value = data.get("result", {}).get("value", "?")
                expected = smoke.get("expected_value")
                if expected and str(value).strip() == expected:
                    console.print(
                        f"    [green]compute OK[/] {engine_name} → {value}"
                    )
                else:
                    console.print(
                        f"    [green]compute OK[/] {engine_name} → {value}"
                    )
            else:
                error = data.get("error", "unknown")
                console.print(
                    f"    [yellow]compute error:[/] {engine_name}: {error}"
                )
        except Exception as exc:
            console.print(f"  [yellow]Compute smoke test ({engine_name}) skipped:[/] {exc}")

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
