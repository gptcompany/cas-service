"""Cascade runner for setup steps — check, install, verify pattern."""

from __future__ import annotations

from typing import Protocol

import questionary
from rich.console import Console
from rich.table import Table


class SetupStep(Protocol):
    name: str

    def check(self) -> bool: ...
    def install(self, console: Console) -> bool: ...
    def verify(self) -> bool: ...


def run_steps(steps: list[SetupStep], console: Console) -> bool:
    """Execute setup steps with interactive prompts on failure."""
    results: list[tuple[str, str]] = []
    for step in steps:
        with console.status(f"[bold cyan]Checking {step.name}...[/]"):
            if step.check():
                console.print(f"  [green]ok[/] {step.name} — already configured")
                results.append((step.name, "ok"))
                continue
        if not questionary.confirm(f"Configure {step.name}?", default=True).ask():
            console.print(f"  [yellow]skip[/] {step.name} — skipped")
            results.append((step.name, "skipped"))
            continue
        success = step.install(console)
        if not success:
            action = questionary.select(
                f"{step.name} failed. What to do?",
                choices=["Skip and continue", "Retry", "Abort"],
            ).ask()
            if action == "Abort":
                console.print("[bold red]Setup aborted.[/]")
                return False
            if action == "Retry":
                success = step.install(console)
                if not success:
                    console.print(
                        f"  [red]fail[/] {step.name} — retry failed, skipping"
                    )
                    results.append((step.name, "failed"))
                    continue
            else:
                results.append((step.name, "skipped"))
                continue
        if step.verify():
            console.print(f"  [green]ok[/] {step.name} — verified!")
            results.append((step.name, "ok"))
        else:
            console.print(
                f"  [yellow]warn[/] {step.name} — installed but verify failed"
            )
            results.append((step.name, "warn"))
    console.print()
    _print_summary(results, console)
    return all(s != "failed" for _, s in results)


def _print_summary(results: list[tuple[str, str]], console: Console) -> None:
    """Print a summary table of all setup results."""
    table = Table(title="Setup Summary", show_lines=False)
    table.add_column("Step", style="bold")
    table.add_column("Status")
    status_map = {
        "ok": "[green]OK[/]",
        "skipped": "[yellow]Skipped[/]",
        "failed": "[red]Failed[/]",
        "warn": "[yellow]Warning[/]",
    }
    for name, status in results:
        table.add_row(name, status_map.get(status, status))
    console.print(table)
