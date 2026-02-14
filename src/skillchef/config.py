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
}


def load() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    return tomllib.loads(CONFIG_PATH.read_text())


def save(cfg: dict[str, Any]) -> None:
    SKILLCHEF_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_bytes(tomli_w.dumps(cfg).encode())


def editor(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load()
    return cfg.get("editor") or os.environ.get("EDITOR", "vim")


def platform_skill_dir(platform: str) -> Path:
    return PLATFORMS[platform]


def ensure_store() -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    return STORE_DIR
