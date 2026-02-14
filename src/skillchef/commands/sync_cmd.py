from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillchef import config, merge, remote, store, ui
from skillchef.llm import selected_key, semantic_merge

from .common import cleanup_fetched, ensure_config, open_editor


@dataclass
class SyncPlan:
    name: str
    fetched_dir: Path
    old_base: str
    new_remote: str
    current_live: str | None
    flavor_text: str
    has_flavor: bool
    has_conflicts: bool


class MergeStrategy:
    def __init__(self, *, ai_available: bool, scope: str) -> None:
        self.ai_available = ai_available
        self.scope = scope

    def start_ai_merge(
        self, *, old_base: str, new_remote: str, flavor_text: str, current_live: str
    ) -> tuple[Future[str] | None, ThreadPoolExecutor | None]:
        if not self.ai_available:
            return None, None
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            semantic_merge,
            old_base,
            new_remote,
            flavor_text,
            None,
            current_live,
            None,
            self.scope,
        )
        return future, executor

    def initial_semantic_check_proposal(
        self,
        *,
        old_base: str,
        new_remote: str,
        flavor_text: str,
        current_live: str,
        deterministic_proposal: str,
    ) -> str | None:
        if not self.ai_available:
            return None
        ai_future, ai_executor = self.start_ai_merge(
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

    def resolve_with_chat(
        self,
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
                    scope=self.scope,
                )
        except Exception as e:
            ui.warn(f"  AI merge failed: {e}")
            return None

    def conflict_choices(self, proposal: str | None) -> list[str]:
        choices = ["accept + re-apply flavor", "keep current", "manual edit"]
        if self.ai_available:
            choices.insert(0, "resolve with chat")
        if proposal:
            choices.insert(0, "accept ai merge")
        return choices


class ConflictResolver:
    def __init__(self, *, strategy: MergeStrategy, scope: str) -> None:
        self.strategy = strategy
        self.scope = scope

    def resolve_without_flavor(self, plan: SyncPlan) -> None:
        if ui.confirm("Accept update?"):
            store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
            store.rebuild_live(plan.name, scope=self.scope)
            ui.success(f"  {plan.name}: updated")
            return
        ui.info(f"  {plan.name}: skipped")

    def resolve_without_conflicts(self, plan: SyncPlan) -> None:
        if plan.current_live is None:
            return
        proposed_live = merge.merge_skill_text(plan.new_remote, plan.flavor_text)
        ui.info("No merge conflicts detected. Local `## Local Flavor` is preserved unchanged.")
        ui.show_diff(
            merge.diff_texts(plan.current_live, proposed_live, "current", "proposed update")
        )

        ai_proposal = self.strategy.initial_semantic_check_proposal(
            old_base=plan.old_base,
            new_remote=plan.new_remote,
            flavor_text=plan.flavor_text,
            current_live=plan.current_live,
            deterministic_proposal=proposed_live,
        )
        if ai_proposal:
            ui.info("AI detected a potential semantic conflict and proposed an alternative merge:")
            ui.show_diff(merge.diff_texts(plan.current_live, ai_proposal, "current", "ai proposed"))

        choices = ["accept update", "keep current", "manual edit"]
        if ai_proposal:
            choices.insert(0, "accept ai merge")
        action = ui.choose("How to handle?", choices)

        if action == "accept ai merge" and ai_proposal:
            store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
            _write_live_skill(plan.name, ai_proposal, scope=self.scope)
            ui.success(f"  {plan.name}: AI merged")
            return
        if action == "accept update":
            store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
            _write_live_skill(plan.name, proposed_live, scope=self.scope)
            ui.success(f"  {plan.name}: updated")
            return
        if action == "keep current":
            ui.info(f"  {plan.name}: skipped")
            return
        if action == "manual edit":
            store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
            _write_live_skill(plan.name, proposed_live, scope=self.scope)
            open_editor(
                store.skill_dir(plan.name, scope=self.scope) / "live" / "SKILL.md", scope=self.scope
            )
            ui.success(f"  {plan.name}: manually merged")

    def resolve_with_conflicts(self, plan: SyncPlan) -> None:
        if plan.current_live is None:
            return
        ai_future, ai_executor = self.strategy.start_ai_merge(
            old_base=plan.old_base,
            new_remote=plan.new_remote,
            flavor_text=plan.flavor_text,
            current_live=plan.current_live,
        )
        proposal = _resolve_ai_future(ai_future)
        if ai_executor:
            ai_executor.shutdown(wait=False)

        if proposal:
            ui.info("AI proposed a semantic merge:")
            ui.show_diff(merge.diff_texts(plan.current_live, proposal, "current", "ai proposed"))

        while True:
            action = ui.choose("How to handle?", self.strategy.conflict_choices(proposal))

            if action == "accept ai merge" and proposal:
                store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
                _write_live_skill(plan.name, proposal, scope=self.scope)
                ui.success(f"  {plan.name}: AI merged")
                return

            if action == "resolve with chat" and self.strategy.ai_available:
                instruction = ui.ask("How should AI resolve this merge?")
                proposal = self.strategy.resolve_with_chat(
                    old_base=plan.old_base,
                    new_remote=plan.new_remote,
                    flavor_text=plan.flavor_text,
                    current_live=plan.current_live,
                    instruction=instruction,
                )
                if proposal:
                    ui.info("Updated AI proposal:")
                    ui.show_diff(
                        merge.diff_texts(plan.current_live, proposal, "current", "ai proposed")
                    )
                continue

            if action == "accept + re-apply flavor":
                store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
                store.rebuild_live(plan.name, scope=self.scope)
                ui.success(f"  {plan.name}: rebased with flavor")
                return

            if action == "keep current":
                ui.info(f"  {plan.name}: skipped")
                return

            if action == "manual edit":
                store.update_base(plan.name, plan.fetched_dir, scope=self.scope)
                store.rebuild_live(plan.name, scope=self.scope)
                open_editor(
                    store.skill_dir(plan.name, scope=self.scope) / "live" / "SKILL.md",
                    scope=self.scope,
                )
                ui.success(f"  {plan.name}: manually merged")
                return


class SyncPlanner:
    def __init__(self, *, meta: dict[str, Any], ai_available: bool, scope: str) -> None:
        self.meta = meta
        self.ai_available = ai_available
        self.scope = scope
        self.name = str(meta["name"])
        self.strategy = MergeStrategy(ai_available=ai_available, scope=scope)
        self.resolver = ConflictResolver(strategy=self.strategy, scope=scope)

    def execute(self) -> None:
        ui.info(f"Syncing [bold]{self.name}[/bold]...")
        try:
            fetched_dir, _ = remote.fetch(str(self.meta["remote_url"]))
        except Exception as e:
            ui.warn(f"  Could not fetch {self.name}: {e}")
            return

        try:
            if store.hash_dir(fetched_dir) == self.meta.get("base_sha256"):
                ui.success(f"  {self.name}: up to date")
                return

            plan = self._build_plan(fetched_dir)
            if not plan.has_flavor:
                self.resolver.resolve_without_flavor(plan)
                return

            if plan.has_conflicts:
                self.resolver.resolve_with_conflicts(plan)
                return

            self.resolver.resolve_without_conflicts(plan)
        finally:
            cleanup_fetched(fetched_dir)

    def _build_plan(self, fetched_dir: Path) -> SyncPlan:
        old_base = store.base_skill_text(self.name, scope=self.scope)
        skill_path = fetched_dir / "SKILL.md"
        new_remote = skill_path.read_text() if skill_path.exists() else ""
        ui.show_diff(merge.diff_texts(old_base, new_remote, "base (current)", "remote (new)"))

        has_flavor = store.has_flavor(self.name, scope=self.scope)
        if not has_flavor:
            return SyncPlan(
                name=self.name,
                fetched_dir=fetched_dir,
                old_base=old_base,
                new_remote=new_remote,
                current_live=None,
                flavor_text="",
                has_flavor=False,
                has_conflicts=False,
            )

        current_live = store.live_skill_text(self.name, scope=self.scope)
        flavor_text = _effective_flavor_text(self.name, current_live, scope=self.scope)
        has_conflicts = merge.has_non_flavor_local_changes(old_base, current_live)
        return SyncPlan(
            name=self.name,
            fetched_dir=fetched_dir,
            old_base=old_base,
            new_remote=new_remote,
            current_live=current_live,
            flavor_text=flavor_text,
            has_flavor=True,
            has_conflicts=has_conflicts,
        )


def run(skill_name: str | None, no_ai: bool, scope: str = "auto") -> None:
    ui.banner()
    ensure_config(scope=scope)

    cfg = config.load(scope=scope)
    key = selected_key(cfg.get("llm_api_key_env", ""))
    ai_available = key is not None and not no_ai
    if ai_available and key:
        ui.info(f"Using [bold]{key[0]}[/bold] ({key[1]}) for semantic merge")

    skills = store.list_skills(scope=scope)
    if not skills:
        ui.info("No skills to sync.")
        return

    if skill_name:
        skills = [s for s in skills if s["name"] == skill_name]
        if not skills:
            ui.error(f"Skill '{skill_name}' not found.")
            raise SystemExit(1)

    for meta in skills:
        _sync_one(meta, ai_available=ai_available, scope=scope)


def _sync_one(meta: dict[str, Any], ai_available: bool = False, scope: str = "auto") -> None:
    SyncPlanner(meta=meta, ai_available=ai_available, scope=scope).execute()


def _effective_flavor_text(name: str, current_live: str, scope: str = "auto") -> str:
    _, live_flavor = merge.split_local_flavor_section(current_live)
    if live_flavor is not None:
        return live_flavor.strip()
    return store.flavor_path(name, scope=scope).read_text()


def _write_live_skill(name: str, content: str, scope: str = "auto") -> None:
    live_md = store.skill_dir(name, scope=scope) / "live" / "SKILL.md"
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
