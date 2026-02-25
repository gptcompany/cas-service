"""Cascade runner for setup steps — check, install, verify pattern."""

from __future__ import annotations

from typing import Protocol

import questionary
from rich.console import Console
from rich.table import Table


class SetupStep(Protocol):
    name: str
    description: str

    def check(self) -> bool: ...
    def install(self, console: Console) -> bool: ...
    def verify(self) -> bool: ...


def _run_single_step(step: SetupStep, console: Console) -> str:
    """Execute a single step and return a status string."""
    with console.status(f"[bold cyan]Checking {step.name}...[/]"):
        if step.check():
            console.print(f"  [green]ok[/] {step.name} — already configured")
            return "ok"

    confirm = questionary.confirm(f"Configure {step.name}?", default=True).ask()
    if confirm is None:
        console.print("[bold red]Setup cancelled.[/]")
        return "abort"
    if not confirm:
        console.print(f"  [yellow]skip[/] {step.name} — skipped")
        return "skipped"

    success = step.install(console)
    if not success:
        action = questionary.select(
            f"{step.name} failed. What to do?",
            choices=["Skip and continue", "Retry", "Abort"],
        ).ask()
        if action is None:
            console.print("[bold red]Setup cancelled.[/]")
            return "abort"
        if action == "Abort":
            console.print("[bold red]Setup aborted.[/]")
            return "abort"
        if action == "Retry":
            success = step.install(console)
            if not success:
                console.print(f"  [red]fail[/] {step.name} — retry failed, skipping")
                return "failed"
        else:
            return "skipped"

    if step.verify():
        console.print(f"  [green]ok[/] {step.name} — verified!")
        return "ok"

    console.print(f"  [yellow]warn[/] {step.name} — installed but verify failed")
    return "warn"


def run_steps(steps: list[SetupStep], console: Console) -> bool:
    """Execute setup steps with interactive prompts on failure."""
    results: list[tuple[str, str]] = []
    for step in steps:
        status = _run_single_step(step, console)
        if status == "abort":
            return False
        results.append((step.name, status))
    console.print()
    _print_summary(results, console)
    return all(s != "failed" for _, s in results)


def run_interactive_menu(steps: list[SetupStep], console: Console) -> bool:
    """Interactive menu with step status and free navigation."""
    session_statuses: list[str] = ["pending"] * len(steps)
    stale_indexes: set[int] = set(range(len(steps)))

    def _checked_status(index: int, step: SetupStep) -> str:
        try:
            if step.check():
                return "ok"
        except Exception:
            pass
        current = session_statuses[index]
        if current in {"skipped", "failed", "warn"}:
            return current
        return "pending"

    def _refresh_indexes(indexes: set[int]) -> None:
        for index in sorted(indexes):
            session_statuses[index] = _checked_status(index, steps[index])
            stale_indexes.discard(index)

    def _snapshot() -> list[str]:
        if stale_indexes:
            _refresh_indexes(set(stale_indexes))
        return list(session_statuses)

    def _invalidate_from(index: int) -> None:
        stale_indexes.update(range(index, len(steps)))

    try:
        while True:
            statuses = _snapshot()
            _print_menu(steps, statuses, console)

            pending_indexes = [
                i
                for i, status in enumerate(statuses)
                if status in {"pending", "failed"}
            ]
            choices: list[object] = []
            for index, step in enumerate(steps, 1):
                status_icon = {
                    "ok": "✅",
                    "pending": "⬜",
                    "failed": "❌",
                    "skipped": "⏭️",
                    "warn": "⚠️",
                }.get(statuses[index - 1], "⬜")
                desc = getattr(step, "description", "")
                label = f"{status_icon} {index:2d}. {step.name}"
                if desc:
                    label += f"  ({desc})"
                choices.append(questionary.Choice(label, value=index - 1))

            choices.append(
                questionary.Choice(
                    f">>> Run all pending ({len(pending_indexes)} steps)",
                    value="run_all",
                )
            )
            choices.append(questionary.Choice(">>> Exit", value="exit"))

            selected = questionary.select("Select step:", choices=choices).ask()
            if selected is None or selected == "exit":
                break

            if selected == "run_all":
                if not pending_indexes:
                    console.print("  [green]All steps already configured.[/]")
                    continue
                aborted = False
                for index in pending_indexes:
                    status = _run_single_step(steps[index], console)
                    if status == "abort":
                        _invalidate_from(index)
                        aborted = True
                        break
                    session_statuses[index] = status
                    # Later steps often depend on earlier ones (Python -> SymPy, Service -> Verify).
                    _invalidate_from(index)
                if aborted:
                    console.print("  [yellow]Run-all aborted — back to menu.[/]")
                continue

            step = steps[int(selected)]
            status = _run_single_step(step, console)
            if status == "abort":
                console.print("  [yellow]Step aborted — back to menu.[/]")
            else:
                selected_index = int(selected)
                session_statuses[selected_index] = status
                _invalidate_from(selected_index)
    except KeyboardInterrupt:
        console.print()
        console.print("[bold yellow]Setup interrupted (Ctrl+C). Exiting menu.[/]")

    final_statuses = _snapshot()
    console.print()
    _print_summary(
        [(step.name, final_statuses[i]) for i, step in enumerate(steps)],
        console,
    )
    return all(status not in {"pending", "failed"} for status in final_statuses)


def _print_menu(steps: list[SetupStep], statuses: list[str], console: Console) -> None:
    """Print the navigable setup menu with current step status."""
    table = Table(title="CAS Setup Wizard", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Step", style="bold")
    table.add_column("Status")

    status_map = {
        "ok": "[green]OK[/]",
        "pending": "[dim]Pending[/]",
        "skipped": "[yellow]Skipped[/]",
        "failed": "[red]Failed[/]",
        "warn": "[yellow]Warning[/]",
    }
    for index, step in enumerate(steps, 1):
        table.add_row(str(index), step.name, status_map.get(statuses[index - 1], statuses[index - 1]))

    console.print()
    table.caption = (
        "Select a step to run it, or use 'Run all pending' to execute remaining steps."
    )
    console.print(table)


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
        "pending": "[dim]Pending[/]",
        "abort": "[red]Aborted[/]",
    }
    for name, status in results:
        table.add_row(name, status_map.get(status, status))
    console.print(table)
