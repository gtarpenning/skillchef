from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from skillchef import config, merge, remote, store, ui

from .common import cleanup_fetched, ensure_config


def run(source: str, force_overwrite: bool = False, scope: str = "auto") -> None:
    ui.banner()
    cfg = ensure_config(scope=scope)

    try:
        sources = _resolve_sources_for_cook(source)
    except Exception as e:
        ui.error(f"Invalid source: {e}")
        raise SystemExit(1)

    platforms = ui.multi_choose(
        "Target platforms", cfg.get("platforms", list(config.PLATFORMS.keys()))
    )

    for resolved_source in sources:
        ui.info(f"Fetching from {resolved_source}...")
        try:
            fetched_dir, remote_type = remote.fetch(resolved_source)
        except Exception as e:
            ui.error(f"Failed to fetch: {e}")
            raise SystemExit(1)

        try:
            default_name = _default_skill_name(fetched_dir)
            while True:
                name = ui.ask("Skill name", default=default_name)
                try:
                    name = store.validate_skill_name(name)
                    break
                except ValueError as ve:
                    ui.warn(str(ve))
            name = _resolve_existing_name(name, force_overwrite=force_overwrite, scope=scope)
            store.cook(name, fetched_dir, resolved_source, remote_type, platforms, scope=scope)
        except Exception as e:
            ui.error(f"Failed to cook skill: {e}")
            raise SystemExit(1)
        finally:
            cleanup_fetched(fetched_dir)

        ui.success(f"Cooked [bold]{name}[/bold]!")
        for p in platforms:
            ui.info(f"Symlinked → {config.platform_skill_dir(p) / name}")


def _resolve_sources_for_cook(source: str) -> list[str]:
    kind = remote.classify(source)
    if kind != "local":
        return [source]

    candidates = remote.local_skill_candidates(source)
    if not candidates:
        raise ValueError("No SKILL.md files found in local source")
    if len(candidates) == 1:
        return [str(candidates[0].parent)]

    root = Path(source).resolve()
    labels = [str(p.parent.relative_to(root)) for p in candidates]
    selected_labels = ui.multi_choose(
        "Multiple local skills found. Which should be cooked?",
        labels,
    )
    selected = [candidates[labels.index(label)] for label in selected_labels]
    return [str(path.parent) for path in selected]


def _default_skill_name(fetched_dir: Path) -> str:
    skill_md = fetched_dir / "SKILL.md"
    default_name = fetched_dir.name
    if not skill_md.exists():
        return default_name

    front, _ = merge.split_frontmatter(skill_md.read_text())
    if "name:" not in front:
        return default_name

    for line in front.splitlines():
        if line.strip().startswith("name:"):
            parsed_name = line.split(":", 1)[1].strip().strip('"').strip("'")
            if parsed_name:
                return parsed_name
            break
    return default_name


def _resolve_existing_name(name: str, *, force_overwrite: bool, scope: str = "auto") -> str:
    existing_dir = store.skill_dir(name, scope=scope)
    if not existing_dir.exists():
        return name

    if force_overwrite:
        return name

    if not ui.can_use_interactive_selector():
        ui.error(f"Skill '{name}' already exists. Re-run with --force-overwrite to replace it.")
        raise SystemExit(1)

    action = ui.choose(
        f"Skill '{name}' already exists. How should we proceed?",
        ["rename", "overwrite", "backup-and-overwrite", "cancel"],
    )

    if action == "rename":
        return _choose_new_name(name, scope=scope)
    if action == "overwrite":
        if ui.confirm(f"Overwrite existing skill '{name}'?", default=False):
            return name
        ui.info("Cook canceled.")
        raise SystemExit(1)
    if action == "backup-and-overwrite":
        _backup_existing_skill(name, scope=scope)
        return name

    ui.info("Cook canceled.")
    raise SystemExit(1)


def _choose_new_name(original: str, scope: str = "auto") -> str:
    while True:
        candidate = ui.ask("New skill name", default=f"{original}-copy").strip()
        try:
            candidate = store.validate_skill_name(candidate)
        except ValueError as ve:
            ui.warn(str(ve))
            continue
        if not store.skill_dir(candidate, scope=scope).exists():
            return candidate
        ui.warn(f"Skill '{candidate}' already exists. Choose another name.")


def _backup_existing_skill(name: str, scope: str = "auto") -> Path:
    src = store.skill_dir(name, scope=scope)
    backups_root = config.scope_home(scope=scope) / "backups"
    backups_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = backups_root / f"{name}-{stamp}"
    suffix = 1
    while dest.exists():
        suffix += 1
        dest = backups_root / f"{name}-{stamp}-{suffix}"

    shutil.move(str(src), str(dest))
    ui.info(f"Backed up existing skill to {dest}")
    return dest
