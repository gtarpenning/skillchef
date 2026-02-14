from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from pathlib import Path
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
    new_remote = (
        (fetched_dir / "SKILL.md").read_text() if (fetched_dir / "SKILL.md").exists() else ""
    )
    ui.show_diff(merge.diff_texts(old_base, new_remote, "base (current)", "remote (new)"))

    if not store.has_flavor(name):
        _sync_without_flavor(name, fetched_dir)
        cleanup_fetched(fetched_dir)
        return

    _sync_with_flavor(
        name=name,
        fetched_dir=fetched_dir,
        old_base=old_base,
        new_remote=new_remote,
        ai_available=ai_available,
    )
    cleanup_fetched(fetched_dir)


def _sync_without_flavor(name: str, fetched_dir: Path) -> None:
    if ui.confirm("Accept update?"):
        store.update_base(name, fetched_dir)
        store.rebuild_live(name)
        ui.success(f"  {name}: updated")
    else:
        ui.info(f"  {name}: skipped")


def _sync_with_flavor(
    *, name: str, fetched_dir: Path, old_base: str, new_remote: str, ai_available: bool
) -> None:
    current_live = store.live_skill_text(name)
    flavor_text = _effective_flavor_text(name, current_live)

    if not merge.has_non_flavor_local_changes(old_base, current_live):
        _sync_without_conflicts(
            name=name,
            fetched_dir=fetched_dir,
            old_base=old_base,
            new_remote=new_remote,
            current_live=current_live,
            flavor_text=flavor_text,
            ai_available=ai_available,
        )
        return

    _sync_with_conflicts(
        name=name,
        fetched_dir=fetched_dir,
        old_base=old_base,
        new_remote=new_remote,
        current_live=current_live,
        flavor_text=flavor_text,
        ai_available=ai_available,
    )


def _sync_without_conflicts(
    *,
    name: str,
    fetched_dir: Path,
    old_base: str,
    new_remote: str,
    current_live: str,
    flavor_text: str,
    ai_available: bool,
) -> None:
    proposed_live = merge.merge_skill_text(new_remote, flavor_text)
    ui.info("No merge conflicts detected. Local `## Local Flavor` is preserved unchanged.")
    ui.show_diff(merge.diff_texts(current_live, proposed_live, "current", "proposed update"))

    ai_proposal = _initial_semantic_check_proposal(
        ai_available=ai_available,
        old_base=old_base,
        new_remote=new_remote,
        flavor_text=flavor_text,
        current_live=current_live,
        deterministic_proposal=proposed_live,
    )
    if ai_proposal:
        ui.info("AI detected a potential semantic conflict and proposed an alternative merge:")
        ui.show_diff(merge.diff_texts(current_live, ai_proposal, "current", "ai proposed"))

    choices = ["accept update", "keep current", "manual edit"]
    if ai_proposal:
        choices.insert(0, "accept ai merge")
    action = ui.choose("How to handle?", choices)

    if action == "accept ai merge" and ai_proposal:
        store.update_base(name, fetched_dir)
        _write_live_skill(name, ai_proposal)
        ui.success(f"  {name}: AI merged")
    elif action == "accept update":
        store.update_base(name, fetched_dir)
        _write_live_skill(name, proposed_live)
        ui.success(f"  {name}: updated")
    elif action == "keep current":
        ui.info(f"  {name}: skipped")
    elif action == "manual edit":
        store.update_base(name, fetched_dir)
        _write_live_skill(name, proposed_live)
        open_editor(store.skill_dir(name) / "live" / "SKILL.md")
        ui.success(f"  {name}: manually merged")


def _sync_with_conflicts(
    *,
    name: str,
    fetched_dir: Path,
    old_base: str,
    new_remote: str,
    current_live: str,
    flavor_text: str,
    ai_available: bool,
) -> None:
    ai_future, ai_executor = _start_ai_merge(
        ai_available=ai_available,
        old_base=old_base,
        new_remote=new_remote,
        flavor_text=flavor_text,
        current_live=current_live,
    )
    ai_result = _resolve_ai_future(ai_future)
    if ai_executor:
        ai_executor.shutdown(wait=False)

    proposal = ai_result
    if proposal:
        ui.info("AI proposed a semantic merge:")
        ui.show_diff(merge.diff_texts(current_live, proposal, "current", "ai proposed"))

    while True:
        action = ui.choose("How to handle?", _conflict_choices(ai_available, proposal))

        if action == "accept ai merge" and proposal:
            store.update_base(name, fetched_dir)
            _write_live_skill(name, proposal)
            ui.success(f"  {name}: AI merged")
            return

        if action == "resolve with chat" and ai_available:
            instruction = ui.ask("How should AI resolve this merge?")
            proposal = _resolve_with_chat(
                old_base=old_base,
                new_remote=new_remote,
                flavor_text=flavor_text,
                current_live=current_live,
                instruction=instruction,
            )
            if proposal:
                ui.info("Updated AI proposal:")
                ui.show_diff(merge.diff_texts(current_live, proposal, "current", "ai proposed"))
            continue

        if action == "accept + re-apply flavor":
            store.update_base(name, fetched_dir)
            store.rebuild_live(name)
            ui.success(f"  {name}: rebased with flavor")
            return

        if action == "keep current":
            ui.info(f"  {name}: skipped")
            return

        if action == "manual edit":
            store.update_base(name, fetched_dir)
            store.rebuild_live(name)
            open_editor(store.skill_dir(name) / "live" / "SKILL.md")
            ui.success(f"  {name}: manually merged")
            return


def _start_ai_merge(
    *,
    ai_available: bool,
    old_base: str,
    new_remote: str,
    flavor_text: str,
    current_live: str,
) -> tuple[Future[str] | None, ThreadPoolExecutor | None]:
    if not ai_available:
        return None, None
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        semantic_merge,
        old_base,
        new_remote,
        flavor_text,
        None,
        current_live,
    )
    return future, executor


def _initial_semantic_check_proposal(
    *,
    ai_available: bool,
    old_base: str,
    new_remote: str,
    flavor_text: str,
    current_live: str,
    deterministic_proposal: str,
) -> str | None:
    if not ai_available:
        return None
    ai_future, ai_executor = _start_ai_merge(
        ai_available=ai_available,
        old_base=old_base,
        new_remote=new_remote,
        flavor_text=flavor_text,
        current_live=current_live,
    )
    ai_result = _resolve_ai_future(ai_future)
    if ai_executor:
        ai_executor.shutdown(wait=False)
    if not ai_result:
        return None
    if _normalize_compare_text(ai_result) == _normalize_compare_text(deterministic_proposal):
        ui.info("AI check: no semantic conflicts detected.")
        return None
    return ai_result


def _resolve_with_chat(
    *,
    old_base: str,
    new_remote: str,
    flavor_text: str,
    current_live: str,
    instruction: str,
) -> str | None:
    if not instruction.strip():
        ui.warn("  No instruction provided.")
        return None
    try:
        with ui.spinner("Waiting for AI merge proposal..."):
            return semantic_merge(
                old_base=old_base,
                new_remote=new_remote,
                flavor=flavor_text,
                current_live=current_live,
                instruction=instruction.strip(),
            )
    except Exception as e:
        ui.warn(f"  AI merge failed: {e}")
        return None


def _conflict_choices(ai_available: bool, proposal: str | None) -> list[str]:
    choices = ["accept + re-apply flavor", "keep current", "manual edit"]
    if ai_available:
        choices.insert(0, "resolve with chat")
    if proposal:
        choices.insert(0, "accept ai merge")
    return choices


def _effective_flavor_text(name: str, current_live: str) -> str:
    _, live_flavor = merge.split_local_flavor_section(current_live)
    if live_flavor is not None:
        live_flavor = live_flavor.strip()
        flavor_path = store.flavor_path(name)
        if flavor_path.read_text().strip() != live_flavor:
            flavor_path.write_text(live_flavor + ("\n" if live_flavor else ""))
        return live_flavor
    return store.flavor_path(name).read_text()


def _write_live_skill(name: str, content: str) -> None:
    live_md = store.skill_dir(name) / "live" / "SKILL.md"
    live_md.write_text(content)


def _normalize_compare_text(text: str) -> str:
    return text.rstrip("\n")


def _resolve_ai_future(future: Future[str] | None) -> str | None:
    if future is None:
        return None
    ui.info("Press Delete to skip AI proposal.")
    try:
        with ui.spinner("Waiting for AI merge proposal..."):
            while True:
                try:
                    return future.result(timeout=0.2)
                except TimeoutError:
                    if ui.poll_delete_key():
                        ui.info("  Skipping initial AI proposal.")
                        return None
    except Exception as e:
        ui.warn(f"  AI merge failed: {e}")
        return None
