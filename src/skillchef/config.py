from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

SKILLCHEF_HOME = Path.home() / ".skillchef"
CONFIG_PATH = SKILLCHEF_HOME / "config.toml"
STORE_DIR = SKILLCHEF_HOME / "store"

PLATFORMS: dict[str, Path] = {
    "codex": Path.home() / ".codex" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
    "claude-code": Path.home() / ".claude" / "skills",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "platforms": [],
    "editor": "",
    "model": "anthropic/claude-sonnet-4-5",
    "llm_api_key_env": "",
    "default_scope": "global",
}


def _load_from_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    return tomllib.loads(path.read_text())


def load(
    scope: str = "global", cwd: Path | None = None, cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    return _load_from_path(config_file_path(scope=scope, cwd=cwd, cfg=cfg))


def save(
    cfg: dict[str, Any],
    scope: str = "global",
    cwd: Path | None = None,
    base_cfg: dict[str, Any] | None = None,
) -> None:
    path = config_file_path(scope=scope, cwd=cwd, cfg=base_cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tomli_w.dumps(cfg).encode())


def editor(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load(scope="global")
    return cfg.get("editor") or os.environ.get("EDITOR", "vim")


def platform_skill_dir(platform: str) -> Path:
    return PLATFORMS[platform]


def resolve_scope(
    scope: str = "auto", cwd: Path | None = None, cfg: dict[str, Any] | None = None
) -> str:
    if scope in {"global", "project"}:
        return scope
    project_home = (cwd or Path.cwd()) / ".skillchef"
    if project_home.exists():
        return "project"
    loaded = cfg or _load_from_path(CONFIG_PATH)
    preferred = str(loaded.get("default_scope", "global")).strip().lower()
    if preferred in {"global", "project"}:
        return preferred
    return "global"


def scope_home(
    scope: str = "auto", cwd: Path | None = None, cfg: dict[str, Any] | None = None
) -> Path:
    resolved = resolve_scope(scope=scope, cwd=cwd, cfg=cfg)
    if resolved == "project":
        return (cwd or Path.cwd()) / ".skillchef"
    return SKILLCHEF_HOME


def config_file_path(
    scope: str = "auto", cwd: Path | None = None, cfg: dict[str, Any] | None = None
) -> Path:
    return scope_home(scope=scope, cwd=cwd, cfg=cfg) / "config.toml"


def store_dir(
    scope: str = "auto", cwd: Path | None = None, cfg: dict[str, Any] | None = None
) -> Path:
    home = scope_home(scope=scope, cwd=cwd, cfg=cfg)
    return home / "store"


def ensure_store(
    scope: str = "auto", cwd: Path | None = None, cfg: dict[str, Any] | None = None
) -> Path:
    out = store_dir(scope=scope, cwd=cwd, cfg=cfg)
    out.mkdir(parents=True, exist_ok=True)
    return out
