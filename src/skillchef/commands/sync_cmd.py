from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from skillchef import config, merge, remote, store, ui
from skillchef.llm import selected_key, semantic_merge

from .common import cleanup_fetched, ensure_config, open_editor


def run(skill_name: str | None, no_ai: bool) -> None:
    ui.banner()
    ensure_config()

    cfg = config.load()
    key = selected_key(cfg.get("llm_api_key_env", ""))
    ai_available = key is not None and not no_ai
    if ai_available and key:
        ui.info(f"Using [bold]{key[0]}[/bold] ({key[1]}) for semantic merge")

    skills = store.list_skills()
    if not skills:
        ui.info("No skills to sync.")
        return

    if skill_name:
        skills = [s for s in skills if s["name"] == skill_name]
        if not skills:
            ui.error(f"Skill '{skill_name}' not found.")
            raise SystemExit(1)

    for meta in skills:
        _sync_one(meta, ai_available=ai_available)


def _sync_one(meta: dict[str, Any], ai_available: bool = False) -> None:
    name = meta["name"]
    ui.info(f"Syncing [bold]{name}[/bold]...")

    try:
        fetched_dir, _ = remote.fetch(meta["remote_url"])
    except Exception as e:
        ui.warn(f"  Could not fetch {name}: {e}")
        return

    new_hash = store.hash_dir(fetched_dir)
    if new_hash == meta.get("base_sha256"):
        ui.success(f"  {name}: up to date")
        cleanup_fetched(fetched_dir)
        return

    old_base = store.base_skill_text(name)
    new_remote = (fetched_dir / "SKILL.md").read_text() if (fetched_dir / "SKILL.md").exists() else ""
    diff_lines = merge.diff_texts(old_base, new_remote, "base (current)", "remote (new)")

    ai_future: Future[str] | None = None
    flavor_text = ""
    if store.has_flavor(name) and ai_available:
        flavor_text = store.flavor_path(name).read_text()
        executor = ThreadPoolExecutor(max_workers=1)
        ai_future = executor.submit(semantic_merge, old_base, new_remote, flavor_text)

    ui.show_diff(diff_lines)

    if not store.has_flavor(name):
        if ui.confirm("Accept update?"):
            store.update_base(name, fetched_dir)
            store.rebuild_live(name)
            ui.success(f"  {name}: updated")
        else:
            ui.info(f"  {name}: skipped")
    else:
        if not flavor_text:
            flavor_text = store.flavor_path(name).read_text()

        ai_result = _resolve_ai_future(ai_future)
        choices = ["accept + re-apply flavor", "keep current", "manual edit"]
        if ai_result:
            choices.insert(0, "accept ai merge")
            ui.info("AI proposed a semantic merge:")
            ai_diff = merge.diff_texts(store.live_skill_text(name), ai_result, "current", "ai proposed")
            ui.show_diff(ai_diff)

        action = ui.choose("How to handle?", choices)

        if action == "accept ai merge" and ai_result:
            store.update_base(name, fetched_dir)
            live_md = store.skill_dir(name) / "live" / "SKILL.md"
            live_md.write_text(ai_result)
            ui.success(f"  {name}: AI merged")
        elif action == "accept + re-apply flavor":
            store.update_base(name, fetched_dir)
            store.rebuild_live(name)
            ui.success(f"  {name}: rebased with flavor")
        elif action == "keep current":
            ui.info(f"  {name}: skipped")
        elif action == "manual edit":
            store.update_base(name, fetched_dir)
            store.rebuild_live(name)
            open_editor(store.skill_dir(name) / "live" / "SKILL.md")
            ui.success(f"  {name}: manually merged")

    cleanup_fetched(fetched_dir)


def _resolve_ai_future(future: Future[str] | None) -> str | None:
    if future is None:
        return None
    try:
        with ui.spinner("Waiting for AI merge proposal..."):
            return future.result(timeout=60)
    except Exception as e:
        ui.warn(f"  AI merge failed: {e}")
        return None
