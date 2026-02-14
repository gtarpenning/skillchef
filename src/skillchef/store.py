from __future__ import annotations

import hashlib
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w

from skillchef import config
from skillchef.merge import merge_skill


def skill_dir(name: str) -> Path:
    return config.ensure_store() / name


def list_skills() -> list[dict[str, Any]]:
    store = config.STORE_DIR
    if not store.exists():
        return []
    skills = []
    for d in sorted(store.iterdir()):
        meta_path = d / "meta.toml"
        if d.is_dir() and meta_path.exists():
            skills.append(load_meta(d.name))
    return skills


def load_meta(name: str) -> dict[str, Any]:
    meta_path = skill_dir(name) / "meta.toml"
    return tomllib.loads(meta_path.read_text())


def save_meta(name: str, meta: dict[str, Any]) -> None:
    meta_path = skill_dir(name) / "meta.toml"
    meta_path.write_bytes(tomli_w.dumps(meta).encode())


def cook(
    name: str, fetched_dir: Path, remote_url: str, remote_type: str, platforms: list[str]
) -> Path:
    """Install a fetched skill into the store."""
    sd = skill_dir(name)
    base_dir = sd / "base"
    live_dir = sd / "live"

    if sd.exists():
        shutil.rmtree(sd)
    sd.mkdir(parents=True)

    shutil.copytree(fetched_dir, base_dir)
    shutil.copytree(base_dir, live_dir)

    meta = {
        "name": name,
        "remote_url": remote_url,
        "remote_type": remote_type,
        "base_sha256": hash_dir(base_dir),
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "platforms": platforms,
    }
    save_meta(name, meta)
    _create_symlinks(name, platforms)
    return sd


def remove(name: str) -> None:
    meta = load_meta(name)
    _remove_symlinks(name, meta.get("platforms", []))
    shutil.rmtree(skill_dir(name))


def update_base(name: str, fetched_dir: Path) -> None:
    sd = skill_dir(name)
    base_dir = sd / "base"
    if base_dir.exists():
        shutil.rmtree(base_dir)
    shutil.copytree(fetched_dir, base_dir)
    meta = load_meta(name)
    meta["base_sha256"] = hash_dir(base_dir)
    meta["last_sync"] = datetime.now(timezone.utc).isoformat()
    save_meta(name, meta)


def rebuild_live(name: str) -> None:
    sd = skill_dir(name)
    live_dir = sd / "live"
    if live_dir.exists():
        shutil.rmtree(live_dir)
    shutil.copytree(sd / "base", live_dir)
    flavor_path = sd / "flavor.md"
    if flavor_path.exists():
        merge_skill(live_dir / "SKILL.md", flavor_path)


def has_flavor(name: str) -> bool:
    return (skill_dir(name) / "flavor.md").exists()


def flavor_path(name: str) -> Path:
    return skill_dir(name) / "flavor.md"


def base_skill_text(name: str) -> str:
    return (skill_dir(name) / "base" / "SKILL.md").read_text()


def live_skill_text(name: str) -> str:
    return (skill_dir(name) / "live" / "SKILL.md").read_text()


def hash_dir(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(path).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _create_symlinks(name: str, platforms: list[str]) -> None:
    live_dir = skill_dir(name) / "live"
    for p in platforms:
        target = config.platform_skill_dir(p) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink() if target.is_symlink() else shutil.rmtree(target)
        target.symlink_to(live_dir)


def _remove_symlinks(name: str, platforms: list[str]) -> None:
    for p in platforms:
        target = config.platform_skill_dir(p) / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)
