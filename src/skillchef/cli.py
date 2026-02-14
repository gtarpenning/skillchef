from __future__ import annotations

import click

from skillchef.commands import (
    cook_cmd,
    flavor_cmd,
    init_cmd,
    inspect_cmd,
    remove_cmd,
    sync_cmd,
)
from skillchef.commands import (
    list_cmd as list_command,
)

SCOPE_CHOICES = ["auto", "global", "project"]


def with_scope_option(help_text: str = "Storage scope to use."):
    return click.option(
        "--scope",
        type=click.Choice(SCOPE_CHOICES),
        default="auto",
        show_default=True,
        help=help_text,
    )


@click.group()
def main() -> None:
    """skillchef — cook, flavor & sync your agent skills."""
    pass


@main.command()
@with_scope_option("Where to save config.")
def init(scope: str) -> None:
    """First-time setup: platforms, editor, model."""
    init_cmd.run(scope=scope)


@main.command()
@click.argument("source")
@click.option(
    "--force-overwrite",
    is_flag=True,
    help="Overwrite an existing skill with the same name without prompting.",
)
@with_scope_option()
def cook(source: str, force_overwrite: bool, scope: str) -> None:
    """Import a skill from a remote source or local path."""
    cook_cmd.run(source, force_overwrite=force_overwrite, scope=scope)


@main.command()
@click.argument("skill_name", required=False)
@click.option("--no-ai", is_flag=True, help="Disable automatic AI merge proposals.")
@with_scope_option()
def sync(skill_name: str | None, no_ai: bool, scope: str) -> None:
    """Check remotes for updates and merge."""
    sync_cmd.run(skill_name, no_ai, scope=scope)


@main.command()
@click.argument("skill_name", required=False)
@with_scope_option()
def flavor(skill_name: str | None, scope: str) -> None:
    """Add or edit a local flavor for a skill."""
    flavor_cmd.run(skill_name, scope=scope)


@main.command(name="list")
@with_scope_option()
def list_cmd(scope: str) -> None:
    """List all managed skills."""
    list_command.run(scope=scope)


@main.command()
@click.argument("skill_name", required=False)
@with_scope_option()
def inspect(skill_name: str | None, scope: str) -> None:
    """Inspect one managed skill (metadata + live SKILL.md), or choose interactively."""
    inspect_cmd.run(skill_name, scope=scope)


@main.command()
@click.argument("skill_name")
@with_scope_option()
def remove(skill_name: str, scope: str) -> None:
    """Remove a managed skill."""
    remove_cmd.run(skill_name, scope=scope)


if __name__ == "__main__":
    main()
