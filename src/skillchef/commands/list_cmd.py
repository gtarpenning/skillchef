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
    names = [str(s["name"]) for s in skills]
    skill_by_name = {str(s["name"]): s for s in skills}

    ui.info("Select a skill to inspect (Esc/Ctrl-C to exit).")
    while True:
        selected = ui.choose_optional("View skill", names)
        if not selected:
            return

        skill = skill_by_name[selected]
        inspect_cmd.inspect_skill_from_meta_with_actions(skill, scope=scope)
