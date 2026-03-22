from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skillchef import config, merge, remote, store, ui
from skillchef.commands.common import cleanup_fetched


@dataclass(frozen=True)
class PublishPlan:
    kind: str
    mode: str
    public: bool = False
    target: str = ""


def run(skill_name: str, scope: str = "auto") -> None:
    ui.banner()
    try:
        meta = store.load_meta(skill_name, scope=scope)
    except FileNotFoundError:
        ui.error(f"Skill '{skill_name}' not found.")
        raise SystemExit(1)

    live_dir = store.skill_dir(skill_name, scope=scope) / "live"
    if not (live_dir / "SKILL.md").exists():
        ui.error(f"Skill '{skill_name}' does not have a live SKILL.md to publish.")
        raise SystemExit(1)

    credentials = remote.detect_publish_credentials()
    _report_credentials(credentials)
    existing = _existing_publish(meta)
    if existing and existing.kind == "gist" and not _is_single_file_skill(live_dir):
        ui.warn(
            "This skill is recorded as a gist and contains multiple files. "
            "Choose a repository target."
        )
        existing = None

    try:
        if existing:
            outcome = _update_existing_publish(
                skill_name,
                live_dir=live_dir,
                existing=existing,
                credentials=credentials,
                scope=scope,
            )
        else:
            outcome = _create_new_publish(
                skill_name,
                live_dir=live_dir,
                credentials=credentials,
                scope=scope,
            )
    except remote.PublishError as e:
        ui.error(f"Failed to publish skill: {e}")
        raise SystemExit(1)

    store.record_served(
        skill_name,
        url=outcome.url,
        kind=outcome.kind,
        visibility=outcome.visibility,
        repo=outcome.repo,
        scope=scope,
    )
    _maybe_update_global_repo_default(outcome, scope=scope)
    _report_publish_result(skill_name, outcome)
    _maybe_recook_from_served_skill(skill_name, outcome, scope=scope)


@dataclass(frozen=True)
class PublishOutcome:
    url: str
    kind: str
    visibility: str
    repo: str = ""


@dataclass(frozen=True)
class ExistingPublish:
    url: str
    kind: str
    visibility: str
    repo: str


def _choose_publish_target(
    skill_name: str,
    live_dir: Path,
    credentials: remote.PublishCredentials,
    *,
    scope: str,
) -> PublishPlan:
    single_file = _is_single_file_skill(live_dir)
    if not credentials.gh_authenticated:
        if credentials.git_configured:
            ui.warn(
                "Git credentials/config detected, but GitHub CLI is not authenticated. "
                "Run `gh auth login` to publish with skillchef."
            )
        elif credentials.gh_installed:
            ui.warn("GitHub CLI is installed but not authenticated. Run `gh auth login` first.")
        else:
            ui.warn("GitHub CLI is not installed. Install `gh` and run `gh auth login` first.")
        raise SystemExit(1)

    default_target = _global_default_repo_target(scope=scope)
    if single_file:
        ui.info(
            f"GitHub CLI credentials detected for [bold]{skill_name}[/bold]. "
            "A gist is the default for single-file skills."
        )
    else:
        ui.info(
            f"GitHub CLI credentials detected for [bold]{skill_name}[/bold]. "
            "Choose an existing destination or create a new repository."
        )

    while True:
        choices = _first_publish_choices(single_file=single_file, default_target=default_target)
        action = ui.choose("Publish target", choices)

        if action == "cancel":
            ui.info("Serve canceled.")
            raise SystemExit(1)

        if action.startswith("use configured default"):
            plan = _plan_for_default_target(default_target, single_file=single_file)
            if plan is not None:
                return plan
            continue

        if action == "github gist (secret)":
            return PublishPlan(kind="gist", mode="create", public=False)
        if action == "github gist (public)":
            return PublishPlan(kind="gist", mode="create", public=True)
        if action == "existing github gist":
            target = ui.ask(
                "Existing gist URL",
                default=default_target if _configured_target_kind(default_target) == "gist" else "",
            ).strip()
            if target:
                return PublishPlan(kind="gist", mode="update", target=target)
            ui.warn("Gist URL cannot be empty.")
            continue
        if action == "existing github repo (overwrite contents)":
            target = ui.ask(
                "Existing repository (OWNER/REPO or URL)",
                default=default_target if _configured_target_kind(default_target) == "repo" else "",
            ).strip()
            if target:
                return PublishPlan(kind="repo", mode="update", target=target)
            ui.warn("Repository target cannot be empty.")
            continue
        if action == "create new github repo (private)":
            repo_name = ui.ask("Repository name", default=skill_name).strip()
            if repo_name:
                return PublishPlan(kind="repo", mode="create", public=False, target=repo_name)
            ui.warn("Repository name cannot be empty.")
            continue
        if action == "create new github repo (public)":
            repo_name = ui.ask("Repository name", default=skill_name).strip()
            if repo_name:
                return PublishPlan(kind="repo", mode="create", public=True, target=repo_name)
            ui.warn("Repository name cannot be empty.")
            continue


def _is_single_file_skill(live_dir: Path) -> bool:
    files = sorted(
        path.relative_to(live_dir).as_posix() for path in live_dir.rglob("*") if path.is_file()
    )
    return files == ["SKILL.md"]


def _existing_publish(meta: dict[str, object]) -> ExistingPublish | None:
    url = str(meta.get("served_url", "")).strip()
    kind = str(meta.get("served_kind", "")).strip()
    visibility = str(meta.get("served_visibility", "")).strip()
    repo = str(meta.get("served_repo", "")).strip()
    if not url or not kind:
        return None
    return ExistingPublish(url=url, kind=kind, visibility=visibility or "private", repo=repo)


def _create_new_publish(
    skill_name: str,
    *,
    live_dir: Path,
    credentials: remote.PublishCredentials,
    scope: str,
    description: str | None = None,
) -> PublishOutcome:
    target = _choose_publish_target(skill_name, live_dir, credentials, scope=scope)
    publish_description = (
        description if description is not None else _publish_description(skill_name)
    )

    if target.kind == "gist" and target.mode == "create":
        url = remote.create_gist(
            [live_dir / "SKILL.md"],
            description=publish_description,
            public=target.public,
        )
        return PublishOutcome(
            url=url,
            kind="gist",
            visibility="public" if target.public else "private",
        )

    if target.kind == "gist" and target.mode == "update":
        url = remote.update_gist(
            target.target,
            [live_dir / "SKILL.md"],
            description=publish_description,
        )
        return PublishOutcome(
            url=url,
            kind="gist",
            visibility="",
        )

    if target.kind == "repo" and target.mode == "create":
        url = remote.create_repo(
            live_dir,
            repo_name=target.target,
            description=publish_description,
            public=target.public,
        )
        return PublishOutcome(
            url=url,
            kind="repo",
            visibility="public" if target.public else "private",
            repo=target.target,
        )

    url = remote.update_repo(
        target.target,
        live_dir,
        description=publish_description,
    )
    return PublishOutcome(
        url=url,
        kind="repo",
        visibility="",
        repo=_repo_name_from_url(target.target),
    )


def _update_existing_publish(
    skill_name: str,
    *,
    live_dir: Path,
    existing: ExistingPublish,
    credentials: remote.PublishCredentials,
    scope: str,
) -> PublishOutcome:
    ui.info(f"[bold]{skill_name}[/bold] is served at {existing.url}")
    changed = _show_served_changes(skill_name, live_dir=live_dir, scope=scope)
    if changed:
        if not ui.confirm(f"Re-serve changes to the existing {existing.kind}?", default=True):
            ui.info("Serve canceled.")
            raise SystemExit(1)
    else:
        ui.info("No local changes detected between `live/` and the served snapshot.")
        if not ui.confirm(f"Re-serve [bold]{skill_name}[/bold] anyway?", default=False):
            ui.info("Serve canceled.")
            raise SystemExit(1)

    description = _publish_description(skill_name)
    try:
        if existing.kind == "gist":
            url = remote.update_gist(
                existing.url,
                [live_dir / "SKILL.md"],
                description=description,
            )
            return PublishOutcome(
                url=url,
                kind="gist",
                visibility=existing.visibility,
            )

        repo_name = existing.repo or _repo_name_from_url(existing.url)
        url = remote.update_repo(
            repo_name,
            live_dir,
            description=description,
        )
        return PublishOutcome(
            url=url,
            kind="repo",
            visibility=existing.visibility,
            repo=repo_name,
        )
    except remote.PublishError as exc:
        if not _is_missing_remote_error(exc):
            raise
        ui.warn(f"Recorded {existing.kind} remote could not be found: {existing.url}")
        if not ui.confirm("Choose a new publish target for this skill?", default=True):
            ui.info("Serve canceled.")
            raise SystemExit(1)
        return _create_new_publish(
            skill_name,
            live_dir=live_dir,
            credentials=credentials,
            scope=scope,
            description=description,
        )


def _show_served_changes(skill_name: str, *, live_dir: Path, scope: str) -> bool:
    if not store.served_snapshot_exists(skill_name, scope=scope):
        ui.info("No previous served snapshot was found for diffing.")
        return True

    served_dir = store.served_snapshot_dir(skill_name, scope=scope)
    diff_lines = _diff_directories(served_dir, live_dir)
    if diff_lines:
        ui.show_diff(diff_lines)
        return True
    return False


def _diff_directories(old_dir: Path, new_dir: Path) -> list[str]:
    old_files = {
        path.relative_to(old_dir).as_posix(): path for path in old_dir.rglob("*") if path.is_file()
    }
    new_files = {
        path.relative_to(new_dir).as_posix(): path for path in new_dir.rglob("*") if path.is_file()
    }
    diff_lines: list[str] = []

    for rel_path in sorted(set(old_files) | set(new_files)):
        old_path = old_files.get(rel_path)
        new_path = new_files.get(rel_path)
        if old_path is None and new_path is not None:
            diff_lines.extend(
                merge.diff_texts(
                    "", new_path.read_text(), f"{rel_path} (served)", f"{rel_path} (current)"
                )
            )
            continue
        if old_path is not None and new_path is None:
            diff_lines.extend(
                merge.diff_texts(
                    old_path.read_text(), "", f"{rel_path} (served)", f"{rel_path} (current)"
                )
            )
            continue
        if old_path is None or new_path is None:
            continue
        if old_path.read_bytes() == new_path.read_bytes():
            continue
        try:
            old_text = old_path.read_text()
            new_text = new_path.read_text()
        except UnicodeDecodeError:
            diff_lines.append(f"Binary file changed: {rel_path}\n")
            continue
        diff_lines.extend(
            merge.diff_texts(old_text, new_text, f"{rel_path} (served)", f"{rel_path} (current)")
        )

    return diff_lines


def _report_publish_result(skill_name: str, outcome: PublishOutcome) -> None:
    published_as = "gist" if outcome.kind == "gist" else "repository"
    visibility = f"{outcome.visibility} " if outcome.visibility else ""
    ui.success(f"Published [bold]{skill_name}[/bold] as a {visibility}{published_as}.")
    if outcome.url:
        ui.info(f"Remote URL: {outcome.url}")


def _maybe_recook_from_served_skill(
    skill_name: str, outcome: PublishOutcome, *, scope: str
) -> None:
    if not ui.confirm(
        f"Would you like to re-cook [bold]{skill_name}[/bold] from your newly served skill?",
        default=False,
    ):
        return

    meta = store.load_meta(skill_name, scope=scope)
    platforms = [str(platform) for platform in meta.get("platforms", [])]

    try:
        fetched_dir, remote_type = remote.fetch(outcome.url)
    except Exception as e:
        ui.error(f"Failed to fetch newly served skill: {e}")
        raise SystemExit(1)

    try:
        store.cook(skill_name, fetched_dir, outcome.url, remote_type, platforms, scope=scope)
        store.record_served(
            skill_name,
            url=outcome.url,
            kind=outcome.kind,
            visibility=outcome.visibility,
            repo=outcome.repo,
            scope=scope,
        )
    finally:
        cleanup_fetched(fetched_dir)

    ui.success(f"Re-cooked [bold]{skill_name}[/bold] from {outcome.url}.")


def _publish_description(skill_name: str) -> str:
    description = ui.ask("Remote description", default=f"{skill_name} skill").strip()
    if description:
        return description
    return f"{skill_name} skill"


def _repo_name_from_url(url: str) -> str:
    stripped = url.removeprefix("https://github.com/").strip("/")
    if stripped:
        return stripped
    return url.strip()


def _is_missing_remote_error(error: Exception) -> bool:
    message = str(error).strip().lower()
    return any(
        token in message
        for token in (
            "not found",
            "http 404",
            "404",
            "repository not found",
            "could not resolve to a repository",
        )
    )


def _first_publish_choices(*, single_file: bool, default_target: str) -> list[str]:
    choices: list[str] = []
    if default_target:
        choices.append(f"use configured default ({_display_target(default_target)})")

    if single_file:
        choices.extend(
            [
                "github gist (secret)",
                "github gist (public)",
                "existing github gist",
                "existing github repo (overwrite contents)",
                "create new github repo (private)",
                "create new github repo (public)",
                "cancel",
            ]
        )
        return choices

    choices.extend(
        [
            "existing github repo (overwrite contents)",
            "create new github repo (private)",
            "create new github repo (public)",
            "cancel",
        ]
    )
    return choices


def _configured_target_kind(target: str) -> str:
    candidate = target.strip()
    if not candidate:
        return ""
    if "gist.github.com" in candidate:
        return "gist"
    if candidate.startswith("https://github.com/") or candidate.count("/") == 1:
        return "repo"
    return ""


def _plan_for_default_target(default_target: str, *, single_file: bool) -> PublishPlan | None:
    kind = _configured_target_kind(default_target)
    if not kind:
        ui.warn("Configured default serve target is not a supported GitHub gist or repository.")
        return None
    if kind != "repo":
        ui.warn("Configured default serve target must be a repository.")
        return None
    return PublishPlan(kind=kind, mode="update", target=default_target)


def _display_target(target: str, *, max_len: int = 40) -> str:
    if len(target) <= max_len:
        return target
    return target[: max_len - 1] + "…"


def _global_default_repo_target(*, scope: str) -> str:
    cfg = config.load(scope=scope)
    target = str(cfg.get("default_serve_target", "")).strip()
    if _configured_target_kind(target) != "repo":
        return ""
    return target


def _maybe_update_global_repo_default(outcome: PublishOutcome, *, scope: str) -> None:
    if outcome.kind != "repo" or not outcome.url:
        return

    cfg = config.load(scope=scope)
    current = str(cfg.get("default_serve_target", "")).strip()
    if current == outcome.url:
        return
    cfg["default_serve_target"] = outcome.url
    config.save(cfg, scope=scope)
    ui.info(f"Global default serve target: {outcome.url}")


def _report_credentials(credentials: remote.PublishCredentials) -> None:
    if credentials.gh_authenticated:
        ui.info("GitHub CLI credentials detected.")
    elif credentials.gh_installed:
        ui.warn("GitHub CLI detected, but no authenticated account was found.")
    else:
        ui.warn("GitHub CLI was not found on PATH.")

    if credentials.git_configured:
        ui.info("Git credentials/config detected.")
    elif credentials.git_installed:
        ui.warn("Git is installed, but no credential helper or user identity was detected.")
    else:
        ui.warn("Git was not found on PATH.")
