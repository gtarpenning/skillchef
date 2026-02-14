from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def isolated_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    from skillchef import config

    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))

    skillchef_home = home / ".skillchef"
    config_path = skillchef_home / "config.toml"
    store_dir = skillchef_home / "store"
    platforms = {
        "codex": home / ".codex" / "skills",
        "cursor": home / ".cursor" / "skills",
        "claude-code": home / ".claude" / "skills",
    }

    monkeypatch.setattr(config, "SKILLCHEF_HOME", skillchef_home)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "STORE_DIR", store_dir)
    monkeypatch.setattr(config, "PLATFORMS", platforms)

    return {
        "home": home,
        "skillchef_home": skillchef_home,
        "config_path": config_path,
        "store_dir": store_dir,
        "platform_codex": platforms["codex"],
    }


@pytest.fixture()
def hello_skill_dir() -> Path:
    return PROJECT_ROOT / "tests" / "skills" / "hello-chef"
