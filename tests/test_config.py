from __future__ import annotations

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
