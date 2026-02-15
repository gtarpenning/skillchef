from __future__ import annotations

from pathlib import Path

from skillchef import merge, store, ui

from .common import ensure_config, open_editor


def run(skill_name: str | None, scope: str = "auto") -> None:
    ui.banner()
    ensure_config(scope=scope)

    skills = store.list_skills(scope=scope)
    if not skills:
        ui.info("No skills cooked yet.")
        return

    if not skill_name:
        names = [s["name"] for s in skills]
        skill_name = ui.choose("Which skill?", names)

    fp = store.flavor_path(skill_name, scope=scope)
    if not fp.exists():
        fp.write_text("# Add your local flavor below\n\n")

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
