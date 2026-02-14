from __future__ import annotations

from skillchef import store, ui


def run() -> None:
    ui.banner()
    skills = store.list_skills()
    ui.skill_table(skills, has_flavor_fn=store.has_flavor)
    if not skills or not ui.can_use_interactive_selector():
        return
    _run_viewer(skills)


def _run_viewer(skills: list[dict[str, object]]) -> None:
    names = [str(s["name"]) for s in skills]
    skill_by_name = {str(s["name"]): s for s in skills}

    ui.info("Select a skill to view live SKILL.md (Esc/Ctrl-C to exit).")
    while True:
        selected = ui.choose_optional("View skill", names)
        if not selected:
            return

        skill = skill_by_name[selected]
        ui.info(f"Viewing [bold]{selected}[/bold] from {skill.get('remote_url', '')}")
        try:
            ui.show_skill_md(store.live_skill_text(selected), title=f"{selected}/live/SKILL.md")
        except FileNotFoundError:
            ui.warn(f"Could not find live SKILL.md for '{selected}'.")
