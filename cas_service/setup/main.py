"""CAS Service setup wizard — CLI entry point.

Usage:
    cas-setup            # Run all setup steps
    cas-setup engines    # Check engines only (Maxima, MATLAB, SymPy)
    cas-setup service    # Configure service deployment
    cas-setup verify     # Verify running service health + engines
"""

from __future__ import annotations

import sys

from rich.console import Console

from cas_service.setup._runner import run_steps

BANNER = r"""
  ___   _   ___   ___              _
 / __| /_\ / __| / __| ___ _ ___ _(_) __ ___
| (__ / _ \\__ \ \__ \/ -_) '_\ V / |/ _/ -_)
 \___/_/ \_\___/ |___/\___|_|  \_/|_|\__\___|
                         Setup Wizard
"""


def _all_steps() -> list:
    """Return the full ordered list of setup steps."""
    from cas_service.setup._gap import GapStep
    from cas_service.setup._python import PythonStep
    from cas_service.setup._maxima import MaximaStep
    from cas_service.setup._matlab import MatlabStep
    from cas_service.setup._sage import SageStep
    from cas_service.setup._sympy import SympyStep
    from cas_service.setup._wolframalpha import WolframAlphaStep
    from cas_service.setup._service import ServiceStep
    from cas_service.setup._verify import VerifyStep

    return [
        PythonStep(),
        SympyStep(),
        MaximaStep(),
        GapStep(),
        MatlabStep(),
        SageStep(),
        WolframAlphaStep(),
        ServiceStep(),
        VerifyStep(),
    ]


def _engine_steps() -> list:
    """Return engine-only setup steps."""
    from cas_service.setup._gap import GapStep
    from cas_service.setup._maxima import MaximaStep
    from cas_service.setup._matlab import MatlabStep
    from cas_service.setup._sage import SageStep
    from cas_service.setup._sympy import SympyStep
    from cas_service.setup._wolframalpha import WolframAlphaStep

    return [
        SympyStep(),
        MaximaStep(),
        GapStep(),
        MatlabStep(),
        SageStep(),
        WolframAlphaStep(),
    ]


def _service_steps() -> list:
    """Return service deployment step only."""
    from cas_service.setup._service import ServiceStep

    return [ServiceStep()]


def _verify_steps() -> list:
    """Return verification step only."""
    from cas_service.setup._verify import VerifyStep

    return [VerifyStep()]


SUBCOMMANDS = {
    "engines": (_engine_steps, "Check CAS engines (SymPy, Maxima, GAP, MATLAB, Sage, WA)"),
    "service": (_service_steps, "Configure service deployment"),
    "verify": (_verify_steps, "Verify running service health"),
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
    else:
        console.print("[bold]Running full setup...[/]")
        console.print()
        steps = _all_steps()

    success = run_steps(steps, console)
    if not success:
        sys.exit(1)
    console.print("[bold green]Setup complete.[/]")


if __name__ == "__main__":
    main()
