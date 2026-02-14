from __future__ import annotations

from pathlib import Path

import pytest

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


def test_open_in_file_manager_uses_platform_command(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(common.sys, "platform", "darwin")
    monkeypatch.setattr(common.subprocess, "call", lambda cmd: calls.append(cmd))

    common.open_in_file_manager(Path("/tmp/demo"))

    assert calls == [["open", "-R", "/tmp/demo"]]


def test_open_in_file_manager_errors_when_command_missing(monkeypatch) -> None:
    errors: list[str] = []
    monkeypatch.setattr(common.sys, "platform", "darwin")
    monkeypatch.setattr(
        common.subprocess, "call", lambda _cmd: (_ for _ in ()).throw(FileNotFoundError())
    )
    monkeypatch.setattr(common.ui, "error", lambda msg: errors.append(msg))

    with pytest.raises(SystemExit):
        common.open_in_file_manager(Path("/tmp/demo"))

    assert errors


def test_ensure_config_uses_project_scope_when_requested(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project)
    (project / ".skillchef").mkdir(parents=True)

    project_cfg = {
        "platforms": ["codex"],
        "editor": "nvim",
        "model": "openai/gpt-5.2",
        "llm_api_key_env": "",
        "default_scope": "project",
    }
    common.config.save(project_cfg, scope="project")

    loaded = common.ensure_config(scope="project")
    assert loaded["platforms"] == ["codex"]
