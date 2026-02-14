from __future__ import annotations

from pathlib import Path

from skillchef import config


def test_save_and_load_round_trip(isolated_paths: dict[str, str]) -> None:
    payload = {
        "platforms": ["codex", "cursor"],
        "editor": "nvim",
        "model": "openai/gpt-5.2",
    }

    config.save(payload)
    loaded = config.load()

    assert isolated_paths["config_path"].exists()
    assert loaded == payload


def test_editor_prefers_config_then_env(monkeypatch, isolated_paths: dict[str, str]) -> None:
    monkeypatch.setenv("EDITOR", "nano")

    assert config.editor({"editor": "helix"}) == "helix"
    assert config.editor({"editor": ""}) == "nano"
    assert config.editor({"editor": ""}) != "vim"


def test_resolve_scope_prefers_project_dir_when_auto(
    monkeypatch, isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / ".skillchef").mkdir(parents=True)
    monkeypatch.chdir(project)

    assert config.resolve_scope("auto", cfg={"default_scope": "global"}) == "project"


def test_resolve_scope_uses_config_default_when_no_project_dir(
    monkeypatch, isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project)

    assert config.resolve_scope("auto", cfg={"default_scope": "project"}) == "project"
    assert config.resolve_scope("auto", cfg={"default_scope": "global"}) == "global"


def test_save_and_load_round_trip_project_scope(
    monkeypatch, isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project)

    payload = {
        "platforms": ["codex"],
        "editor": "nvim",
        "model": "openai/gpt-5.2",
    }

    config.save(payload, scope="project")
    loaded = config.load(scope="project")

    assert (project / ".skillchef" / "config.toml").exists()
    assert loaded == payload
