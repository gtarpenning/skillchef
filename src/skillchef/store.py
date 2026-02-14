from __future__ import annotations

import hashlib
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w

from skillchef import config, remote
from skillchef.merge import merge_skill


def skill_dir(name: str, scope: str = "auto") -> Path:
    return config.ensure_store(scope=scope) / name


def list_skills(scope: str = "auto") -> list[dict[str, Any]]:
    root = config.store_dir(scope=scope)
    if not root.exists():
        return []
    skills = []
    for d in sorted(root.iterdir()):
        meta_path = d / "meta.toml"
        if d.is_dir() and meta_path.exists():
            skills.append(load_meta(d.name, scope=scope))
    return skills


def load_meta(name: str, scope: str = "auto") -> dict[str, Any]:
    meta_path = skill_dir(name, scope=scope) / "meta.toml"
    return tomllib.loads(meta_path.read_text())


def save_meta(name: str, meta: dict[str, Any], scope: str = "auto") -> None:
    meta_path = skill_dir(name, scope=scope) / "meta.toml"
    meta_path.write_bytes(tomli_w.dumps(meta).encode())


def cook(
    name: str,
    fetched_dir: Path,
    remote_url: str,
    remote_type: str,
    platforms: list[str],
    scope: str = "auto",
) -> Path:
    """Install a fetched skill into the store."""
    sd = skill_dir(name, scope=scope)
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
    meta.update(remote.source_metadata(remote_url, remote_type))
    save_meta(name, meta, scope=scope)
    _create_symlinks(name, platforms, scope=scope)
    return sd


def remove(name: str, scope: str = "auto") -> None:
    meta = load_meta(name, scope=scope)
    _remove_symlinks(name, meta.get("platforms", []), scope=scope)
    shutil.rmtree(skill_dir(name, scope=scope))


def update_base(name: str, fetched_dir: Path, scope: str = "auto") -> None:
    sd = skill_dir(name, scope=scope)
    base_dir = sd / "base"
    if base_dir.exists():
        shutil.rmtree(base_dir)
    shutil.copytree(fetched_dir, base_dir)
    meta = load_meta(name, scope=scope)
    meta.update(remote.source_metadata(meta.get("remote_url", ""), meta.get("remote_type", "")))
    meta["base_sha256"] = hash_dir(base_dir)
    meta["last_sync"] = datetime.now(timezone.utc).isoformat()
    save_meta(name, meta, scope=scope)


def rebuild_live(name: str, scope: str = "auto") -> None:
    sd = skill_dir(name, scope=scope)
    live_dir = sd / "live"
    if live_dir.exists():
        shutil.rmtree(live_dir)
    shutil.copytree(sd / "base", live_dir)
    flavor_path = sd / "flavor.md"
    if flavor_path.exists():
        merge_skill(live_dir / "SKILL.md", flavor_path)


def has_flavor(name: str, scope: str = "auto") -> bool:
    return (skill_dir(name, scope=scope) / "flavor.md").exists()


def flavor_path(name: str, scope: str = "auto") -> Path:
    return skill_dir(name, scope=scope) / "flavor.md"


def base_skill_text(name: str, scope: str = "auto") -> str:
    return (skill_dir(name, scope=scope) / "base" / "SKILL.md").read_text()


def live_skill_text(name: str, scope: str = "auto") -> str:
    return (skill_dir(name, scope=scope) / "live" / "SKILL.md").read_text()


def hash_dir(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(path).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _create_symlinks(name: str, platforms: list[str], scope: str = "auto") -> None:
    live_dir = skill_dir(name, scope=scope) / "live"
    for p in platforms:
        target = config.platform_skill_dir(p) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            raise RuntimeError(
                f"Refusing to overwrite non-symlink platform path: {target}. "
                "Remove it manually or choose a different skill name."
            )
        target.symlink_to(live_dir)


def _remove_symlinks(name: str, platforms: list[str], scope: str = "auto") -> None:
    expected_live = skill_dir(name, scope=scope) / "live"
    for p in platforms:
        target = config.platform_skill_dir(p) / name
        if target.is_symlink():
            if target.resolve(strict=False) == expected_live.resolve(strict=False):
                target.unlink()
                continue
            raise RuntimeError(
                f"Refusing to remove unmanaged symlink: {target} -> {target.resolve(strict=False)}"
            )
        elif target.exists():
            raise RuntimeError(f"Refusing to remove non-symlink platform path: {target}")
