from __future__ import annotations

from skillchef import merge, store, ui

from .common import ensure_config, open_editor


def run(skill_name: str | None) -> None:
    ui.banner()
    ensure_config()

    skills = store.list_skills()
    if not skills:
        ui.info("No skills cooked yet.")
        return

    if not skill_name:
        names = [s["name"] for s in skills]
        skill_name = ui.choose("Which skill?", names)

    fp = store.flavor_path(skill_name)
    if not fp.exists():
        fp.write_text("# Add your local flavor below\n\n")

    old_live = store.live_skill_text(skill_name)
    open_editor(fp)
    store.rebuild_live(skill_name)
    new_live = store.live_skill_text(skill_name)

    diff_lines = merge.diff_texts(old_live, new_live, "before", "after")
    ui.show_diff(diff_lines)
    ui.success(f"Flavor saved for [bold]{skill_name}[/bold]")
