"""CAS Service setup wizard — CLI entry point.

Usage:
    cas-setup            # Run all setup steps
    cas-setup engines    # Check engines only
    cas-setup configure  # Re-configure engine paths and API keys
    cas-setup service    # Configure service deployment
    cas-setup verify     # Verify running service health + engines
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
}


def main(args: list[str] | None = None) -> None:
    """CLI entry point for the setup wizard."""
    console = Console()
    console.print(BANNER, style="bold cyan")

    argv = args if args is not None else sys.argv[1:]

    if len(argv) > 1 or (len(argv) == 1 and argv[0] in ("-h", "--help")):
        console.print("Usage: cas-setup [SUBCOMMAND]")
        console.print()
        console.print("Subcommands:")
        console.print("  (none)     Run all setup steps")
        for name, (_, desc) in SUBCOMMANDS.items():
            console.print(f"  {name:<10} {desc}")
        return

    if len(argv) == 1:
        subcmd = argv[0]
        if subcmd not in SUBCOMMANDS:
            console.print(
                f"[red]Unknown subcommand: {subcmd}[/]  "
                f"(available: {', '.join(SUBCOMMANDS)})"
            )
            sys.exit(1)
        factory, description = SUBCOMMANDS[subcmd]
        console.print(f"[bold]{description}[/]")
        console.print()
        steps = factory()
        success = run_steps(steps, console)
    else:
        _print_welcome(console)
        steps = _all_steps()
        success = run_interactive_menu(steps, console)
    if not success:
        sys.exit(1)
    console.print("[bold green]Setup complete.[/]")


if __name__ == "__main__":
    main()
