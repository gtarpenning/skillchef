from __future__ import annotations

from pathlib import Path

import click

from skillchef import config, ui
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


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """skillchef — cook, flavor & sync your agent skills."""
    if ctx.invoked_subcommand is not None:
        return
    if _is_first_run():
        _run_first_time_entrypoint()
        return
    click.echo(ctx.get_help())


def _is_first_run(cwd: Path | None = None) -> bool:
    workdir = cwd or Path.cwd()
    global_home_exists = config.SKILLCHEF_HOME.exists()
    project_home_exists = (workdir / ".skillchef").exists()
    return not global_home_exists and not project_home_exists


def _run_first_time_entrypoint() -> None:
    ui.banner()
    ui.console.print()
    ui.info("SkillChef has not been set up yet. Choose one option to get started:")
    choice = ui.choose(
        "Get started",
        ["init + onboarding wizard (recommended)", "init only"],
    )
    if choice == "init + onboarding wizard (recommended)":
        init_cmd.run(scope="auto", run_wizard=True)
        return
    init_cmd.run(scope="auto", run_wizard=False)


@main.command()
@click.option(
    "--wizard/--no-wizard",
    default=None,
    help="Run the onboarding wizard after setup. If omitted, skillchef will ask.",
)
@with_scope_option("Where to save config.")
def init(wizard: bool | None, scope: str) -> None:
    """First-time setup: platforms, editor, model."""
    init_cmd.run(scope=scope, run_wizard=wizard)


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
