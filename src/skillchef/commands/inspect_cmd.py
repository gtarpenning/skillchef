from __future__ import annotations

from typing import Any

from skillchef import store, ui
from skillchef.commands.common import open_editor, open_in_file_manager

PREVIEW_LINES = 10
PREVIEW_CHARS = 500


def run(skill_name: str | None, scope: str = "auto") -> None:
    ui.banner()
    meta = _meta_for_name(skill_name, scope=scope) if skill_name else _meta_from_prompt(scope=scope)
    if meta is None:
        return
    inspect_skill_from_meta(meta, scope=scope)
    if ui.can_use_interactive_selector():
        _action_loop(meta, scope=scope)


def inspect_skill_from_meta(meta: dict[str, Any], scope: str = "auto") -> None:
    name = str(meta.get("name", ""))
    flavored = store.has_flavor(name, scope=scope) if name else False
    ui.show_skill_inspect(meta, flavored=flavored)
    try:
        text = store.live_skill_text(name, scope=scope)
        preview, truncated = _skill_preview(text)
        ui.show_skill_md(preview, title=f"{name}/live/SKILL.md")
        if truncated:
            ui.info("Showing compact preview. Choose 'see full skill?' for the full file.")
    except FileNotFoundError:
        ui.warn(f"Could not find live SKILL.md for '{name}'.")


def _meta_for_name(skill_name: str, scope: str = "auto") -> dict[str, Any]:
    for meta in store.list_skills(scope=scope):
        if str(meta.get("name")) == skill_name:
            return meta
    ui.error(f"Skill '{skill_name}' not found.")
    raise SystemExit(1)


def _meta_from_prompt(scope: str = "auto") -> dict[str, Any] | None:
    skills = store.list_skills(scope=scope)
    if not skills:
        ui.error("No skills found. Run [bold]skillchef cook <source>[/bold] first.")
        raise SystemExit(1)

    names = [str(skill.get("name", "")) for skill in skills]
    selected = ui.choose_optional("Inspect skill", names)
    if not selected:
        return None

    for meta in skills:
        if str(meta.get("name")) == selected:
            return meta

    ui.error(f"Skill '{selected}' not found.")
    raise SystemExit(1)


def _skill_preview(text: str) -> tuple[str, bool]:
    if len(text) <= PREVIEW_CHARS and text.count("\n") < PREVIEW_LINES:
        return text, False
    lines = text.splitlines()
    preview = "\n".join(lines[:PREVIEW_LINES]).rstrip()
    if len(preview) > PREVIEW_CHARS:
        preview = preview[:PREVIEW_CHARS].rstrip()
    return f"{preview}\n\n... [truncated]", True


def _action_loop(meta: dict[str, Any], scope: str = "auto") -> None:
    name = str(meta.get("name", "")).strip()
    if not name:
        return

    actions = [
        "see full skill?",
        "open skill in finder",
        "open in editor",
        "done",
    ]
    while True:
        action = ui.choose_optional("Next action", actions)
        if action in (None, "done"):
            return

        if action == "see full skill?":
            try:
                ui.show_skill_md(store.live_skill_text(name, scope=scope), title=f"{name}/live/SKILL.md")
            except FileNotFoundError:
                ui.warn(f"Could not find live SKILL.md for '{name}'.")
        elif action == "open skill in finder":
            try:
                open_in_file_manager(store.skill_dir(name, scope=scope) / "live" / "SKILL.md")
            except SystemExit:
                continue
        elif action == "open in editor":
            try:
                open_editor(store.skill_dir(name, scope=scope) / "live" / "SKILL.md", scope=scope)
            except SystemExit:
                continue
