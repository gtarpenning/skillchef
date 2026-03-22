from __future__ import annotations

from skillchef import store, ui
from skillchef.commands import inspect_cmd


def run(scope: str = "auto") -> None:
    ui.banner()
    skills = store.list_skills(scope=scope)
    ui.skill_table(skills, has_flavor_fn=lambda n: store.has_flavor(n, scope=scope))
    if not skills or not ui.can_use_interactive_selector():
        return
    _run_viewer(skills, scope=scope)


def _run_viewer(skills: list[dict[str, object]], scope: str = "auto") -> None:
    skill_by_name = {str(s["name"]): s for s in skills}

    ui.info("Select a skill to inspect (Esc/Ctrl-C to exit).")
    while True:
        names = list(skill_by_name)
        if not names:
            ui.info("No skills remain.")
            return
        selected = ui.choose_optional("View skill", names)
        if not selected:
            return

        _run_skill_actions(selected, skill_by_name, scope=scope)


def _run_skill_actions(
    name: str, skill_by_name: dict[str, dict[str, object]], scope: str = "auto"
) -> None:
    while True:
        meta = skill_by_name[name]
        enabled = bool(meta.get("enabled", True))
        toggle = "disable" if enabled else "enable"
        action = ui.choose_optional("Action", ["inspect", toggle, "delete", "back"])
        if action in (None, "back"):
            return

        if action == "inspect":
            inspect_cmd.inspect_skill_from_meta_with_actions(meta, scope=scope)
            continue
        if action == "delete":
            if _delete_skill(name, scope=scope, skill_by_name=skill_by_name):
                return
            continue

        _set_enabled(name, enabled=not enabled, scope=scope, skill_by_name=skill_by_name)


def _set_enabled(
    name: str,
    *,
    enabled: bool,
    scope: str,
    skill_by_name: dict[str, dict[str, object]],
) -> None:
    desired = "enabled" if enabled else "disabled"
    try:
        store.set_enabled(name, enabled=enabled, scope=scope)
    except Exception as e:
        ui.error(f"Failed to set '{name}' as {desired}: {e}")
        return

    skill_by_name[name]["enabled"] = enabled
    ui.success(f"{name} is now {desired}.")


def _delete_skill(
    name: str,
    *,
    scope: str,
    skill_by_name: dict[str, dict[str, object]],
) -> bool:
    if not ui.confirm(f"Remove [bold]{name}[/bold]?", default=False):
        return False

    try:
        store.remove(name, scope=scope)
    except Exception as e:
        ui.error(f"Failed to remove '{name}': {e}")
        return False

    skill_by_name.pop(name, None)
    ui.success(f"Removed {name}")
    return True
