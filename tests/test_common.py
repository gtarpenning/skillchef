from __future__ import annotations

from skillchef.commands import common


def test_resolve_editor_command_supports_aliases(monkeypatch) -> None:
    monkeypatch.setattr(common, "EDITOR_FALLBACKS", {})
    monkeypatch.setattr(
        common.shutil, "which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "code" else None
    )

    assert common.resolve_editor_command("vscode") == "code"


def test_discover_editor_suggestions_lists_installed_editors(monkeypatch) -> None:
    monkeypatch.setattr(common, "EDITOR_FALLBACKS", {})
    installed = {"code", "cursor", "nvim", "nano", "zed", "atom", "subl"}
    monkeypatch.setattr(
        common.shutil, "which", lambda cmd: f"/usr/bin/{cmd}" if cmd in installed else None
    )

    suggestions = common.discover_editor_suggestions()

    assert ("Visual Studio Code", "code") in suggestions
    assert ("Cursor", "cursor") in suggestions
    assert ("Neovim", "nvim") in suggestions
    assert ("Nano", "nano") in suggestions
    assert ("Zed", "zed") in suggestions
    assert ("Atom", "atom") in suggestions
    assert ("Sublime Text", "subl") in suggestions
