from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from skillchef import config, ui


def ensure_config() -> dict[str, Any]:
    cfg = config.load()
    if not cfg.get("platforms"):
        ui.warn("No config found. Run [bold]skillchef init[/bold] first.")
        raise SystemExit(1)
    return cfg


def open_editor(path: Path) -> None:
    cfg = config.load()
    ed = config.editor(cfg)
    subprocess.call([ed, str(path)])


def cleanup_fetched(fetched_dir: Path) -> None:
    root = fetched_dir.parent if fetched_dir.name == "skill" else fetched_dir
    shutil.rmtree(root, ignore_errors=True)
