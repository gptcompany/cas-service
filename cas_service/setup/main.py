"""CAS Service setup wizard — CLI entry point.

Usage:
    cas-setup            # Run all setup steps
    cas-setup engines    # Check engines only
    cas-setup configure  # Re-configure engine paths and API keys
    cas-setup service    # Configure service deployment
    cas-setup verify     # Verify running service health + engines
    cas-setup get        # Show config values (or one key)
    cas-setup set        # Set config values (e.g., CAS_PORT)
"""

from __future__ import annotations

import sys

from rich.console import Console

from cas_service.setup._runner import run_interactive_menu, run_steps

BANNER = r"""
  ___   _   ___   ___              _
 / __| /_\ / __| / __| ___ _ ___ _(_) __ ___
| (__ / _ \\__ \ \__ \/ -_) '_\ V / |/ _/ -_)
 \___/_/ \_\___/ |___/\___|_|  \_/|_|\__\___|
                         Setup Wizard
"""


def _all_steps() -> list:
    """Return the full ordered list of setup steps."""
    from cas_service.setup._python import PythonStep
    from cas_service.setup._matlab import MatlabStep
    from cas_service.setup._sage import SageStep
    from cas_service.setup._sympy import SympyStep
    from cas_service.setup._wolframalpha import WolframAlphaStep
    from cas_service.setup._service import ServiceStep
    from cas_service.setup._verify import VerifyStep

    return [
        PythonStep(),
        SympyStep(),
        MatlabStep(),
        SageStep(),
        WolframAlphaStep(),
        ServiceStep(),
        VerifyStep(),
    ]


def _engine_steps() -> list:
    """Return engine-only setup steps."""
    from cas_service.setup._matlab import MatlabStep
    from cas_service.setup._sage import SageStep
    from cas_service.setup._sympy import SympyStep
    from cas_service.setup._wolframalpha import WolframAlphaStep

    return [
        SympyStep(),
        MatlabStep(),
        SageStep(),
        WolframAlphaStep(),
    ]


def _service_steps() -> list:
    """Return service deployment step only."""
    from cas_service.setup._service import ServiceStep

    return [ServiceStep()]


def _configure_steps() -> list:
    """Return engine configuration steps (path prompts, API keys)."""
    from cas_service.setup._matlab import MatlabStep
    from cas_service.setup._sage import SageStep
    from cas_service.setup._wolframalpha import WolframAlphaStep

    return [
        MatlabStep(),
        SageStep(),
        WolframAlphaStep(),
    ]


def _verify_steps() -> list:
    """Return verification step only."""
    from cas_service.setup._verify import VerifyStep

    return [VerifyStep()]


def _print_welcome(console: Console) -> None:
    """Print a short welcome guide for non-technical users."""
    console.print("[bold]Full setup — this wizard will:[/]")
    console.print()
    console.print(
        "  1. Check Python and SymPy     [dim](required, usually pre-installed)[/]"
    )
    console.print("  2. Find MATLAB                [dim](optional, commercial CAS)[/]")
    console.print(
        "  3. Find or install SageMath    [dim](optional, open-source CAS)[/]"
    )
    console.print(
        "  4. Configure WolframAlpha      [dim](optional, remote API — needs key)[/]"
    )
    console.print(
        "  5. Choose how to run           [dim](systemd / Docker / foreground)[/]"
    )
    console.print(
        "  6. Verify everything works     [dim](health check + engine smoke test)[/]"
    )
    console.print()
    console.print(
        "  [dim]Press Enter to accept defaults. Optional engines can be skipped.[/]"
    )
    console.print()


SUBCOMMANDS = {
    "engines": (_engine_steps, "Check CAS engines (SymPy, MATLAB, Sage, WA)"),
    "configure": (_configure_steps, "Re-configure engine paths and API keys"),
    "service": (_service_steps, "Configure service deployment"),
    "verify": (_verify_steps, "Verify running service health + engine smoke tests"),
    "get": (None, "Show configuration values (e.g., 'cas-setup get CAS_PORT')"),
    "set": (None, "Set configuration value (e.g., 'cas-setup set CAS_PORT 8870')"),
}


def _handle_get(args: list[str], console: Console) -> int:
    from cas_service.setup._config import get_key
    from rich.table import Table

    known = [
        "CAS_PORT",
        "CAS_MATLAB_PATH",
        "CAS_SAGE_PATH",
        "CAS_WOLFRAMALPHA_APPID",
        "CAS_LOG_LEVEL",
    ]

    if not args:
        table = Table(title="CAS Configuration", show_lines=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        for key in known:
            val = get_key(key)
            table.add_row(key, val or "[dim]not set[/]")
        console.print(table)
        return 0

    key = args[0]
    val = get_key(key)
    if val:
        print(val)
        return 0
    console.print(f"[red]Error:[/] Key '{key}' not found or not set.")
    return 1


def _handle_set(args: list[str], console: Console) -> int:
    from cas_service.setup._config import parse_cas_port, set_cas_port, write_key

    if len(args) < 2:
        console.print("[red]Usage:[/] cas-setup set <KEY> <VALUE>")
        return 1

    key, value = args[0], args[1]
    if key == "CAS_PORT":
        parsed = parse_cas_port(value)
        if parsed is None:
            console.print(f"[red]Error:[/] Invalid port (1-65535): {value}")
            return 1
        if not set_cas_port(parsed):
            console.print("[red]Failed to set CAS_PORT[/]")
            return 1
        console.print(f"[green]Successfully set CAS_PORT={parsed}[/]")
        return 0

    write_key(key, value)
    console.print(f"[green]Successfully set {key}={value}[/]")
    return 0


def main(args: list[str] | None = None) -> int:
    """CLI entry point for the setup wizard."""
    console = Console()
    console.print(BANNER, style="bold cyan")

    argv = args if args is not None else sys.argv[1:]

    if len(argv) == 1 and argv[0] in ("-h", "--help", "help"):
        console.print("Usage: cas-setup [SUBCOMMAND]")
        console.print()
        console.print("Subcommands:")
        console.print("  (none)     Run all setup steps")
        console.print("  get [KEY]  Show config values")
        console.print("  set <KEY> <VALUE>  Set config value")
        for name, (_, desc) in SUBCOMMANDS.items():
            if name in {"get", "set"}:
                continue
            console.print(f"  {name:<10} {desc}")
        return 0

    if len(argv) == 1:
        subcmd = argv[0]
        if subcmd == "get":
            return _handle_get([], console)
        if subcmd not in SUBCOMMANDS:
            console.print(
                f"[red]Unknown subcommand: {subcmd}[/]  "
                f"(available: {', '.join(SUBCOMMANDS)})"
            )
            sys.exit(1)
        factory, description = SUBCOMMANDS[subcmd]
        if subcmd == "set":
            console.print("[red]Usage:[/] cas-setup set <KEY> <VALUE>")
            return 1
        if factory is None:
            return 1
        console.print(f"[bold]{description}[/]")
        console.print()
        steps = factory()
        success = run_steps(steps, console)
    elif len(argv) >= 2 and argv[0] == "get":
        return _handle_get(argv[1:], console)
    elif len(argv) >= 3 and argv[0] == "set":
        return _handle_set(argv[1:], console)
    elif len(argv) >= 1 and argv[0] == "set":
        console.print("[red]Usage:[/] cas-setup set <KEY> <VALUE>")
        return 1
    else:
        _print_welcome(console)
        steps = _all_steps()
        success = run_interactive_menu(steps, console)
    if not success:
        sys.exit(1)
    console.print("[bold green]Setup complete.[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
