from __future__ import annotations

import sys
from typing import Any, Callable

from questionary import Choice
import questionary
from rich.console import Console
from rich.columns import Columns
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def banner() -> None:
    console.print(Panel.fit("[bold]skillchef[/bold]  ·  cook, flavor & sync your skills", border_style="dim"))


def success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def info(msg: str) -> None:
    console.print(f"[dim]→[/dim] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def ask(prompt: str, default: str = "") -> str:
    return Prompt.ask(f"  {prompt}", default=default, console=console)


def confirm(prompt: str, default: bool = True) -> bool:
    return Confirm.ask(f"  {prompt}", default=default, console=console)


def choose(prompt: str, choices: list[str]) -> str:
    if _can_use_interactive_selector():
        selected = questionary.select(
            f"  {prompt}",
            choices=choices,
            qmark="",
        ).ask()
        if selected:
            return selected

    for i, c in enumerate(choices, 1):
        console.print(f"  [dim]{i}.[/dim] {c}")
    while True:
        val = ask(prompt)
        if val in choices:
            return val
        try:
            idx = int(val) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        warn("Invalid choice, try again")


def multi_choose(prompt: str, choices: list[str]) -> list[str]:
    if _can_use_interactive_selector():
        selected = questionary.checkbox(
            f"  {prompt}",
            choices=[Choice(title=c, value=c, checked=True) for c in choices],
            qmark="",
        ).ask()
        return list(selected) if selected else choices

    for i, c in enumerate(choices, 1):
        console.print(f"  [dim]{i}.[/dim] {c}")
    raw = ask(f"{prompt} (comma-separated numbers)")
    selected = []
    for part in raw.split(","):
        part = part.strip()
        if part in choices:
            selected.append(part)
        else:
            try:
                idx = int(part) - 1
                if 0 <= idx < len(choices):
                    selected.append(choices[idx])
            except ValueError:
                pass
    return selected or choices


def show_diff(diff_lines: list[str]) -> None:
    if not diff_lines:
        info("No differences")
        return
    text = Text()
    for line in diff_lines:
        line_str = line.rstrip("\n")
        if line_str.startswith("+"):
            text.append(line_str + "\n", style="green")
        elif line_str.startswith("-"):
            text.append(line_str + "\n", style="red")
        elif line_str.startswith("@@"):
            text.append(line_str + "\n", style="cyan")
        else:
            text.append(line_str + "\n")
    console.print(Panel(text, title="diff", border_style="dim"))


def skill_table(skills: list[dict[str, Any]], has_flavor_fn: Callable[[str], bool] | None = None) -> None:
    if not skills:
        info("No skills cooked yet. Run [bold]skillchef cook <source>[/bold] to get started.")
        return
    table = Table(show_header=True, header_style="bold", border_style="dim")
    table.add_column("Name")
    table.add_column("Source", style="dim")
    table.add_column("Last Sync", style="dim")
    table.add_column("Flavor", justify="center")
    table.add_column("Platforms", style="dim")
    for s in skills:
        flavored = has_flavor_fn(s["name"]) if has_flavor_fn else False
        flavor = "[green]yes[/green]" if flavored else "[dim]no[/dim]"
        table.add_row(
            s["name"],
            _truncate(s.get("remote_url", ""), 40),
            s.get("last_sync", "")[:10],
            flavor,
            ", ".join(s.get("platforms", [])),
        )
    console.print(table)


def show_platforms(platforms: dict[str, Any]) -> None:
    table = Table(show_header=False, border_style="dim", padding=(0, 2))
    table.add_column("Platform", style="bold")
    table.add_column("Path", style="dim")
    table.add_column("Status")
    for name, path in platforms.items():
        exists = path.exists()
        status = "[green]found[/green]" if exists else "[dim]will create[/dim]"
        table.add_row(name, str(path), status)
    console.print(table)


def show_detected_keys(keys: list[tuple[str, str]]) -> None:
    if not keys:
        info("No LLM API keys detected in environment")
        return
    for env_var, provider in keys:
        success(f"Detected [bold]{env_var}[/bold] ({provider})")


def show_config_summary(cfg: dict[str, Any]) -> None:
    console.print()
    table = Table(show_header=False, border_style="dim", padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Platforms", ", ".join(cfg.get("platforms", [])))
    table.add_row("Editor", cfg.get("editor", ""))
    table.add_row("AI Model", cfg.get("model", ""))
    table.add_row("AI Key", cfg.get("llm_api_key_env", "") or "(auto)")
    console.print(table)


def spinner(msg: str) -> Any:
    return console.status(f"[dim]{msg}[/dim]", spinner="dots")


def show_skill_md(text: str, title: str = "SKILL.md") -> None:
    console.print(Syntax(text, "markdown", theme="monokai", line_numbers=False, word_wrap=True))


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _can_use_interactive_selector() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
