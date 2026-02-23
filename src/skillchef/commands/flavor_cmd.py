from __future__ import annotations

from pathlib import Path

from skillchef import merge, store, ui

from .common import ensure_config, open_editor

FLAVOR_TEMPLATE = "# Add your local flavor below\n\n"


def run(
    skill_name: str | None,
    *,
    flavor_name: str | None = None,
    use_flavor: str | None = None,
    scope: str = "auto",
) -> None:
    ui.banner()
    ensure_config(scope=scope)

    if flavor_name and use_flavor:
        ui.error("Use either --name or --use, not both.")
        raise SystemExit(1)

    skills = store.list_skills(scope=scope)
    if not skills:
        ui.info("No skills cooked yet.")
        return

    if not skill_name:
        names = [s["name"] for s in skills]
        skill_name = ui.choose("Which skill?", names)

    if use_flavor:
        _switch_active_flavor(skill_name, use_flavor, scope=scope)
        return

    if flavor_name:
        fp = _set_active_named_flavor(skill_name, flavor_name, scope=scope)
    else:
        fp = store.flavor_path(skill_name, scope=scope)

    if not fp.exists():
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(FLAVOR_TEMPLATE)

    old_live = store.live_skill_text(skill_name, scope=scope)
    _edit_flavor(fp, scope=scope)
    store.rebuild_live(skill_name, scope=scope)
    new_live = store.live_skill_text(skill_name, scope=scope)

    diff_lines = merge.diff_texts(old_live, new_live, "before", "after")
    ui.show_diff(diff_lines)
    ui.success(f"Flavor saved for [bold]{skill_name}[/bold]")


def _edit_flavor(path: Path, *, scope: str) -> None:
    open_editor(path, scope=scope)
    ui.ask("Done editing? Press Enter after saving your changes", default="")


def _set_active_named_flavor(skill_name: str, flavor_name: str, *, scope: str) -> Path:
    try:
        store.set_active_flavor(skill_name, flavor_name, scope=scope)
    except ValueError as e:
        ui.error(str(e))
        raise SystemExit(1)
    return store.named_flavor_path(skill_name, flavor_name, scope=scope)


def _switch_active_flavor(skill_name: str, flavor_name: str, *, scope: str) -> None:
    try:
        validated = store.validate_flavor_name(flavor_name)
    except ValueError as e:
        ui.error(str(e))
        raise SystemExit(1)

    if not store.flavor_exists(skill_name, validated, scope=scope):
        available = ", ".join(store.list_flavor_names(skill_name, scope=scope))
        suffix = f" Available: {available}" if available else ""
        ui.error(f"Flavor '{validated}' does not exist for '{skill_name}'.{suffix}")
        raise SystemExit(1)

    old_live = store.live_skill_text(skill_name, scope=scope)
    store.set_active_flavor(skill_name, validated, scope=scope)
    store.rebuild_live(skill_name, scope=scope)
    new_live = store.live_skill_text(skill_name, scope=scope)
    ui.show_diff(merge.diff_texts(old_live, new_live, "before", "after"))
    ui.success(f"Active flavor set to [bold]{validated}[/bold] for [bold]{skill_name}[/bold]")
