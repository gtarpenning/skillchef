from __future__ import annotations

import hashlib
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w

from skillchef import config, remote
from skillchef.merge import merge_skill

DEFAULT_FLAVOR_NAME = "default"
_FLAVOR_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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
    if not meta_path.exists():
        raise KeyError(f"Skill '{name}' not found in store.")
    meta = tomllib.loads(meta_path.read_text())
    # Populate default metadata fields when absent.
    meta.setdefault("enabled", True)
    meta.setdefault("active_flavor", DEFAULT_FLAVOR_NAME)
    meta.setdefault("served_url", "")
    meta.setdefault("served_kind", "")
    meta.setdefault("served_visibility", "")
    meta.setdefault("served_repo", "")
    meta.setdefault("served_sha256", "")
    meta.setdefault("last_served", "")
    return meta


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
        "enabled": True,
        "active_flavor": DEFAULT_FLAVOR_NAME,
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
    active_flavor = flavor_path(name, scope=scope)
    if active_flavor.exists():
        merge_skill(live_dir / "SKILL.md", active_flavor)


def write_live_skill(name: str, content: str, scope: str = "auto") -> None:
    rebuild_live(name, scope=scope)
    live_md = skill_dir(name, scope=scope) / "live" / "SKILL.md"
    live_md.write_text(content)


def served_snapshot_dir(name: str, scope: str = "auto") -> Path:
    return skill_dir(name, scope=scope) / "served"


def save_served_snapshot(name: str, source_dir: Path, scope: str = "auto") -> None:
    snapshot_dir = served_snapshot_dir(name, scope=scope)
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    shutil.copytree(source_dir, snapshot_dir)


def served_snapshot_exists(name: str, scope: str = "auto") -> bool:
    return served_snapshot_dir(name, scope=scope).exists()


def record_served(
    name: str,
    *,
    url: str,
    kind: str,
    visibility: str,
    scope: str = "auto",
    repo: str = "",
) -> None:
    live_dir = skill_dir(name, scope=scope) / "live"
    save_served_snapshot(name, live_dir, scope=scope)
    meta = load_meta(name, scope=scope)
    meta["served_url"] = url
    meta["served_kind"] = kind
    meta["served_visibility"] = visibility
    meta["served_repo"] = repo
    meta["served_sha256"] = hash_dir(live_dir)
    meta["last_served"] = datetime.now(timezone.utc).isoformat()
    save_meta(name, meta, scope=scope)


def has_flavor(name: str, scope: str = "auto") -> bool:
    return flavor_path(name, scope=scope).exists()


def set_enabled(name: str, enabled: bool, scope: str = "auto") -> None:
    meta = load_meta(name, scope=scope)
    current = bool(meta.get("enabled", True))
    if current == enabled:
        return

    platforms = [str(p) for p in meta.get("platforms", [])]
    if enabled:
        _create_symlinks(name, platforms, scope=scope)
    else:
        _remove_symlinks(name, platforms, scope=scope)

    meta["enabled"] = enabled
    save_meta(name, meta, scope=scope)


def flavor_path(name: str, scope: str = "auto") -> Path:
    active = active_flavor_name(name, scope=scope)
    return _flavor_path_for_name(name, active, scope=scope)


def flavor_exists(name: str, flavor_name: str, scope: str = "auto") -> bool:
    return _flavor_path_for_name(name, flavor_name, scope=scope).exists()


def set_active_flavor(name: str, flavor_name: str, scope: str = "auto") -> None:
    validated = validate_flavor_name(flavor_name)
    meta = load_meta(name, scope=scope)
    meta["active_flavor"] = validated
    save_meta(name, meta, scope=scope)


def active_flavor_name(name: str, scope: str = "auto") -> str:
    meta = load_meta(name, scope=scope)
    raw = str(meta.get("active_flavor", DEFAULT_FLAVOR_NAME)).strip()
    if not raw:
        return DEFAULT_FLAVOR_NAME
    try:
        return validate_flavor_name(raw)
    except ValueError:
        return DEFAULT_FLAVOR_NAME


def list_flavor_names(name: str, scope: str = "auto") -> list[str]:
    names = {active_flavor_name(name, scope=scope)}
    legacy = _legacy_flavor_path(name, scope=scope)
    if legacy.exists():
        names.add(DEFAULT_FLAVOR_NAME)
    flavors_dir = skill_dir(name, scope=scope) / "flavors"
    if flavors_dir.exists():
        for entry in flavors_dir.glob("*.md"):
            names.add(entry.stem)
    return sorted(names)


def named_flavor_path(name: str, flavor_name: str, scope: str = "auto") -> Path:
    validated = validate_flavor_name(flavor_name)
    return skill_dir(name, scope=scope) / "flavors" / f"{validated}.md"


def validate_skill_name(name: str) -> str:
    candidate = str(name).strip()
    if not candidate:
        raise ValueError("Skill name cannot be empty.")
    if not _FLAVOR_NAME_PATTERN.match(candidate):
        raise ValueError(
            "Skill name must start with a letter/number and only use letters, numbers, '-', '_', '.'."
        )
    return candidate


def validate_flavor_name(flavor_name: str) -> str:
    candidate = str(flavor_name).strip()
    if not candidate:
        raise ValueError("Flavor name cannot be empty.")
    if not _FLAVOR_NAME_PATTERN.match(candidate):
        raise ValueError(
            "Flavor name must start with a letter/number and only use letters, numbers, '-', '_', '.'."
        )
    return candidate


def _flavor_path_for_name(name: str, flavor_name: str, scope: str = "auto") -> Path:
    validated = validate_flavor_name(flavor_name)
    named = named_flavor_path(name, validated, scope=scope)
    if validated != DEFAULT_FLAVOR_NAME:
        return named

    legacy = _legacy_flavor_path(name, scope=scope)
    if named.exists():
        return named
    return legacy


def _legacy_flavor_path(name: str, scope: str = "auto") -> Path:
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
