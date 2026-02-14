from __future__ import annotations

from pathlib import Path

from skillchef import config, merge, remote, store, ui

from .common import cleanup_fetched, ensure_config


def run(source: str) -> None:
    ui.banner()
    cfg = ensure_config()

    try:
        source = _resolve_source_for_cook(source)
    except Exception as e:
        ui.error(f"Invalid source: {e}")
        raise SystemExit(1)

    ui.info(f"Fetching from {source}...")
    try:
        fetched_dir, remote_type = remote.fetch(source)
    except Exception as e:
        ui.error(f"Failed to fetch: {e}")
        raise SystemExit(1)

    skill_md = fetched_dir / "SKILL.md"
    default_name = fetched_dir.name
    if skill_md.exists():
        front, _ = merge.split_frontmatter(skill_md.read_text())
        if "name:" in front:
            for line in front.splitlines():
                if line.strip().startswith("name:"):
                    default_name = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break

    name = ui.ask("Skill name", default=default_name)
    platforms = ui.multi_choose("Target platforms", cfg.get("platforms", list(config.PLATFORMS.keys())))

    store.cook(name, fetched_dir, source, remote_type, platforms)
    cleanup_fetched(fetched_dir)

    ui.success(f"Cooked [bold]{name}[/bold]!")
    for p in platforms:
        ui.info(f"Symlinked → {config.platform_skill_dir(p) / name}")


def _resolve_source_for_cook(source: str) -> str:
    kind = remote.classify(source)
    if kind != "local":
        return source

    candidates = remote.local_skill_candidates(source)
    if not candidates:
        raise ValueError("No SKILL.md files found in local source")
    if len(candidates) == 1:
        return str(candidates[0].parent)

    root = Path(source).resolve()
    labels = [str(p.parent.relative_to(root)) for p in candidates]
    picked = ui.choose("Multiple local skills found. Which one should be cooked?", labels)
    selected = candidates[labels.index(picked)]
    return str(selected.parent)
