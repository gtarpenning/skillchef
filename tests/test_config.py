from __future__ import annotations

from pathlib import Path

from skillchef import config


def test_save_and_load_round_trip(
    monkeypatch, isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    payload = {
        "platforms": ["codex", "cursor"],
        "editor": "nvim",
        "model": "openai/gpt-5.2",
    }

    config.save(payload, scope="global")
    assert isolated_paths["config_path"].exists()
    assert config.load(scope="global") == payload

    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project)
    config.save(payload, scope="project")
    assert (project / ".skillchef" / "config.toml").exists()
    assert config.load(scope="project") == payload


def test_editor_prefers_config_then_env(monkeypatch, isolated_paths: dict[str, str]) -> None:
    monkeypatch.setenv("EDITOR", "nano")

    assert config.editor({"editor": "helix"}) == "helix"
    assert config.editor({"editor": ""}) == "nano"
    assert config.editor({"editor": ""}) != "vim"


def test_resolve_scope_auto_behavior(
    monkeypatch, isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project)

    assert config.resolve_scope("auto", cfg={"default_scope": "project"}) == "project"
    assert config.resolve_scope("auto", cfg={"default_scope": "global"}) == "global"

    (project / ".skillchef").mkdir(parents=True)
    assert config.resolve_scope("auto", cfg={"default_scope": "global"}) == "project"
