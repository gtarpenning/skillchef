from __future__ import annotations

import click

from skillchef.commands import (
    cook_cmd,
    flavor_cmd,
    init_cmd,
    remove_cmd,
    sync_cmd,
)
from skillchef.commands import (
    list_cmd as list_command,
)


@click.group()
def main() -> None:
    """skillchef — cook, flavor & sync your agent skills."""
    pass


@main.command()
def init() -> None:
    """First-time setup: platforms, editor, model."""
    init_cmd.run()


@main.command()
@click.argument("source")
def cook(source: str) -> None:
    """Import a skill from a remote source or local path."""
    cook_cmd.run(source)


@main.command()
@click.argument("skill_name", required=False)
@click.option("--no-ai", is_flag=True, help="Disable automatic AI merge proposals.")
def sync(skill_name: str | None, no_ai: bool) -> None:
    """Check remotes for updates and merge."""
    sync_cmd.run(skill_name, no_ai)


@main.command()
@click.argument("skill_name", required=False)
def flavor(skill_name: str | None) -> None:
    """Add or edit a local flavor for a skill."""
    flavor_cmd.run(skill_name)


@main.command(name="list")
def list_cmd() -> None:
    """List all managed skills."""
    list_command.run()


@main.command()
@click.argument("skill_name")
def remove(skill_name: str) -> None:
    """Remove a managed skill."""
    remove_cmd.run(skill_name)


if __name__ == "__main__":
    main()
