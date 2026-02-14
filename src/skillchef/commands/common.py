from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from skillchef import config, ui

EDITOR_ALIASES = {
    "vscode": "code",
    "visual-studio-code": "code",
    "visual studio code": "code",
    "neovim": "nvim",
    "sublime": "subl",
    "sublime-text": "subl",
    "sublime text": "subl",
}

EDITOR_FALLBACKS = {
    "code": ["/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"],
    "cursor": ["/Applications/Cursor.app/Contents/Resources/app/bin/cursor"],
    "subl": ["/Applications/Sublime Text.app/Contents/SharedSupport/bin/subl"],
}

COMMON_EDITORS = [
    ("Visual Studio Code", ["code", "code-insiders"]),
    ("Cursor", ["cursor"]),
    ("Neovim", ["nvim"]),
    ("Nano", ["nano"]),
    ("Zed", ["zed"]),
    ("Atom", ["atom"]),
    ("Sublime Text", ["subl", "sublime_text"]),
]


def ensure_config(scope: str = "auto") -> dict[str, Any]:
    cfg = config.load(scope=scope)
    if not cfg.get("platforms"):
        ui.warn("No config found for this scope. Run [bold]skillchef init --scope <scope>[/bold].")
        raise SystemExit(1)
    return cfg


def open_editor(path: Path, scope: str = "auto") -> None:
    cfg = config.load(scope=scope)
    ed = resolve_editor_command(config.editor(cfg))
    if not ed:
        ui.error(
            "Editor command not found. Re-run [bold]skillchef init[/bold] and pick an installed editor."
        )
        raise SystemExit(1)
    subprocess.call([ed, str(path)])


def open_in_file_manager(path: Path) -> None:
    if sys.platform == "darwin":
        # -R reveals the target in Finder instead of opening by file association.
        cmd = ["open", "-R", str(path)]
    elif os.name == "nt":
        cmd = ["explorer", str(path)]
    else:
        cmd = ["xdg-open", str(path)]

    try:
        subprocess.call(cmd)
    except FileNotFoundError:
        ui.error("Could not open file manager from this environment.")
        raise SystemExit(1)


def resolve_editor_command(editor: str) -> str | None:
    candidate = editor.strip()
    if not candidate:
        return None

    if shutil.which(candidate):
        return candidate

    normalized = candidate.lower()
    alias = EDITOR_ALIASES.get(normalized)
    if alias and shutil.which(alias):
        return alias

    for fallback in EDITOR_FALLBACKS.get(alias or candidate, []):
        if Path(fallback).exists():
            return fallback
    return None


def discover_editor_suggestions() -> list[tuple[str, str]]:
    suggestions: list[tuple[str, str]] = []
    for label, commands in COMMON_EDITORS:
        for cmd in commands:
            resolved = resolve_editor_command(cmd)
            if resolved:
                suggestions.append((label, resolved))
                break
    return suggestions


def cleanup_fetched(fetched_dir: Path) -> None:
    root = fetched_dir.parent if fetched_dir.name == "skill" else fetched_dir
    shutil.rmtree(root, ignore_errors=True)
