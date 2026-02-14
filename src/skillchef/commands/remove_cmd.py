from __future__ import annotations

from skillchef import store, ui


def run(skill_name: str) -> None:
    ui.banner()
    try:
        store.load_meta(skill_name)
    except FileNotFoundError:
        ui.error(f"Skill '{skill_name}' not found.")
        raise SystemExit(1)

    if ui.confirm(f"Remove [bold]{skill_name}[/bold]?", default=False):
        store.remove(skill_name)
        ui.success(f"Removed {skill_name}")
