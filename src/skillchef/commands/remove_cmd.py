from __future__ import annotations

from skillchef import store, ui


def run(skill_name: str, scope: str = "auto") -> None:
    ui.banner()
    try:
        store.load_meta(skill_name, scope=scope)
    except FileNotFoundError:
        ui.error(f"Skill '{skill_name}' not found.")
        raise SystemExit(1)

    if ui.confirm(f"Remove [bold]{skill_name}[/bold]?", default=False):
        try:
            store.remove(skill_name, scope=scope)
        except Exception as e:
            ui.error(f"Failed to remove '{skill_name}': {e}")
            raise SystemExit(1)
        ui.success(f"Removed {skill_name}")
