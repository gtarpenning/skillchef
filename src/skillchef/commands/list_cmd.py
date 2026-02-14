from __future__ import annotations

from skillchef import store, ui


def run() -> None:
    ui.banner()
    ui.skill_table(store.list_skills(), has_flavor_fn=store.has_flavor)
