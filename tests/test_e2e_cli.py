from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from skillchef import cli, config, store
from skillchef.commands import flavor_cmd, init_cmd, sync_cmd


def _write_skill_dir(path: Path, *, name: str = "demo", body: str = "base v1") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\n---\n\n# Demo\n\n{body}\n")


def _write_folder_skill_dir(
    path: Path,
    *,
    name: str = "test-skill",
    body: str = "base v1",
    script_body: str = "#!/bin/sh\necho v1\n",
    yaml_body: str = "mode: v1\n",
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\n---\n\n# Demo\n\n{body}\n")
    (path / "scripts").mkdir(exist_ok=True)
    (path / "scripts" / "run.sh").write_text(script_body)
    (path / "config").mkdir(exist_ok=True)
    (path / "config" / "recipe.yaml").write_text(yaml_body)


def _mute_ui(monkeypatch) -> None:
    for fn in (
        "banner",
        "info",
        "success",
        "warn",
        "error",
        "show_diff",
        "show_command",
        "show_platforms",
        "show_detected_keys",
        "show_config_summary",
    ):
        monkeypatch.setattr(f"skillchef.ui.{fn}", lambda *_a, **_k: None)


def test_e2e_init_cook_sync_without_flavor(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    source = tmp_path / "remote-skill"
    _write_skill_dir(source, body="base v1")

    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [])
    monkeypatch.setattr(init_cmd, "discover_editor_suggestions", lambda: [])
    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])
    monkeypatch.setattr("skillchef.ui.choose", lambda _p, _c: "global")

    def ask(prompt: str, default: str = "") -> str:
        if "Preferred editor" in prompt:
            return "vim"
        if "AI model for semantic merge" in prompt:
            return "openai/gpt-5.2"
        if "Skill name" in prompt:
            return "demo"
        return default

    monkeypatch.setattr("skillchef.ui.ask", ask)
    monkeypatch.setattr(
        "skillchef.ui.confirm",
        lambda prompt, default=True: False if "Run the onboarding wizard now?" in prompt else True,
    )

    runner = CliRunner()
    assert runner.invoke(cli.main, ["init"]).exit_code == 0
    assert runner.invoke(cli.main, ["cook", str(source)]).exit_code == 0

    _write_skill_dir(source, body="base v2")
    assert runner.invoke(cli.main, ["sync", "demo", "--no-ai"]).exit_code == 0
    assert "base v2" in store.live_skill_text("demo")


def test_e2e_cook_multiple_local_skills_from_parent_dir(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    config.save(
        {
            "platforms": ["codex"],
            "editor": "vim",
            "model": "openai/gpt-5.2",
            "llm_api_key_env": "",
            "default_scope": "global",
        }
    )
    source_root = tmp_path / "skills"
    _write_skill_dir(source_root / "alpha", name="alpha", body="base a")
    _write_skill_dir(source_root / "beta", name="beta", body="base b")

    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, choices: list(choices))
    monkeypatch.setattr("skillchef.ui.ask", lambda _p, default="": default)

    runner = CliRunner()
    result = runner.invoke(cli.main, ["cook", str(source_root)])

    assert result.exit_code == 0
    assert store.load_meta("alpha")["remote_url"] == str(source_root / "alpha")
    assert store.load_meta("beta")["remote_url"] == str(source_root / "beta")
    assert "base a" in store.live_skill_text("alpha")
    assert "base b" in store.live_skill_text("beta")


def test_e2e_init_with_optional_example_wizard(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    monkeypatch.setattr("skillchef.ui.require_exact_command", lambda *_a, **_k: None)
    source = tmp_path / "frontend-design-source"
    _write_skill_dir(source, name="frontend-design", body="base v1")

    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [])
    monkeypatch.setattr(init_cmd, "discover_editor_suggestions", lambda: [])
    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])

    def choose(prompt: str, choices: list[str]) -> str:
        if "Default scope" in prompt:
            return "global"
        if "How to handle?" in prompt:
            return "accept update"
        return choices[0]

    monkeypatch.setattr("skillchef.ui.choose", choose)

    def ask(prompt: str, default: str = "") -> str:
        if "Preferred editor" in prompt:
            return "vim"
        if "AI model for semantic merge" in prompt:
            return "openai/gpt-5.2"
        return default

    monkeypatch.setattr("skillchef.ui.ask", ask)

    def confirm(prompt: str, default: bool = True) -> bool:
        if "Run the onboarding wizard now?" in prompt:
            return True
        if "Open your editor to tweak this flavor now?" in prompt:
            return False
        return default

    monkeypatch.setattr("skillchef.ui.confirm", confirm)

    original_fetch = init_cmd.remote.fetch

    def fake_fetch(source_url: str):
        if source_url == init_cmd.README_EXAMPLE_SOURCE:
            return original_fetch(str(source))
        return original_fetch(source_url)

    monkeypatch.setattr(init_cmd.remote, "fetch", fake_fetch)

    runner = CliRunner()
    assert runner.invoke(cli.main, ["init"]).exit_code == 0

    flavor = store.flavor_path("frontend-design").read_text()
    live = store.live_skill_text("frontend-design")
    assert init_cmd.WIZARD_FLAVOR_TEXT.strip() in flavor
    assert init_cmd.WIZARD_UPDATE_MARKER in live


def test_e2e_sync_with_flavor_preserves_flavor_text(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    config.save(
        {
            "platforms": ["codex"],
            "editor": "vim",
            "model": "openai/gpt-5.2",
            "llm_api_key_env": "",
            "default_scope": "global",
        }
    )
    source = tmp_path / "remote-skill"
    _write_skill_dir(source, body="base v1")

    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])
    monkeypatch.setattr(
        "skillchef.ui.ask",
        lambda prompt, default="": "demo" if "Skill name" in prompt else default,
    )
    runner = CliRunner()
    assert runner.invoke(cli.main, ["cook", str(source)]).exit_code == 0

    monkeypatch.setattr(
        flavor_cmd,
        "open_editor",
        lambda fp, scope="auto": fp.write_text("Keep local behavior\n"),
    )
    assert runner.invoke(cli.main, ["flavor", "demo"]).exit_code == 0

    _write_skill_dir(source, body="base v2")
    monkeypatch.setattr(
        "skillchef.ui.choose",
        lambda _p, _c: "accept update",
    )
    assert runner.invoke(cli.main, ["sync", "demo", "--no-ai"]).exit_code == 0

    live = store.live_skill_text("demo")
    assert "base v2" in live
    assert "Keep local behavior" in live


def test_e2e_sync_folder_skill_refreshes_extra_files(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    config.save(
        {
            "platforms": ["codex"],
            "editor": "vim",
            "model": "openai/gpt-5.2",
            "llm_api_key_env": "",
            "default_scope": "global",
        }
    )
    source_root = tmp_path / "skills"
    source = source_root / "test-skill"
    _write_folder_skill_dir(source, body="base v1")

    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])
    monkeypatch.setattr("skillchef.ui.ask", lambda _p, default="": default)

    runner = CliRunner()
    assert runner.invoke(cli.main, ["cook", str(source_root)]).exit_code == 0

    flavor = store.flavor_path("test-skill")
    flavor.write_text("Keep local behavior\n")
    store.rebuild_live("test-skill")

    live_dir = store.skill_dir("test-skill") / "live"
    assert (live_dir / "scripts" / "run.sh").read_text() == "#!/bin/sh\necho v1\n"
    assert (live_dir / "config" / "recipe.yaml").read_text() == "mode: v1\n"

    _write_folder_skill_dir(
        source,
        body="base v2",
        script_body="#!/bin/sh\necho v2\n",
        yaml_body="mode: v2\n",
    )
    monkeypatch.setattr("skillchef.ui.choose", lambda _p, _c: "accept update")

    assert runner.invoke(cli.main, ["sync", "test-skill", "--no-ai"]).exit_code == 0

    live = store.live_skill_text("test-skill")
    assert "base v2" in live
    assert "Keep local behavior" in live
    assert (live_dir / "scripts" / "run.sh").read_text() == "#!/bin/sh\necho v2\n"
    assert (live_dir / "config" / "recipe.yaml").read_text() == "mode: v2\n"


def test_e2e_sync_accepts_ai_merge_proposal(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    config.save(
        {
            "platforms": ["codex"],
            "editor": "vim",
            "model": "openai/gpt-5.2",
            "llm_api_key_env": "OPENAI_API_KEY",
            "default_scope": "global",
        }
    )
    source = tmp_path / "remote-skill"
    _write_skill_dir(source, body="base v1")
    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])
    monkeypatch.setattr(
        "skillchef.ui.ask", lambda prompt, default="": "demo" if "Skill name" in prompt else default
    )

    runner = CliRunner()
    assert runner.invoke(cli.main, ["cook", str(source)]).exit_code == 0

    flavor_path = store.flavor_path("demo")
    flavor_path.write_text("Flavor X\n")
    store.rebuild_live("demo")
    live_path = store.skill_dir("demo") / "live" / "SKILL.md"
    live_path.write_text("# Demo\n\nmanual local tweak\n\n## Local Flavor\n\nFlavor X\n")

    _write_skill_dir(source, body="base v2")
    monkeypatch.setattr(sync_cmd, "semantic_merge", lambda *_a, **_k: "AI merged output\n")
    monkeypatch.setattr("skillchef.ui.choose", lambda _p, _c: "accept ai merge")

    assert runner.invoke(cli.main, ["sync", "demo"]).exit_code == 0
    assert store.live_skill_text("demo") == "AI merged output\n"


def test_e2e_recook_collision_rename_keeps_both(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    _mute_ui(monkeypatch)
    config.save(
        {
            "platforms": ["codex"],
            "editor": "vim",
            "model": "openai/gpt-5.2",
            "llm_api_key_env": "",
            "default_scope": "global",
        }
    )
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    _write_skill_dir(source_a, body="A")
    _write_skill_dir(source_b, body="B")

    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])

    ask_state = {"new_name_calls": 0}

    def ask(prompt: str, default: str = "") -> str:
        if "New skill name" in prompt:
            ask_state["new_name_calls"] += 1
            return "demo-2"
        if "Skill name" in prompt:
            return "demo"
        return default

    monkeypatch.setattr("skillchef.ui.ask", ask)
    monkeypatch.setattr("skillchef.ui.can_use_interactive_selector", lambda: True)
    monkeypatch.setattr(
        "skillchef.ui.choose",
        lambda prompt, choices: "rename" if "already exists" in prompt else choices[0],
    )

    runner = CliRunner()
    assert runner.invoke(cli.main, ["cook", str(source_a)]).exit_code == 0
    assert runner.invoke(cli.main, ["cook", str(source_b)]).exit_code == 0

    assert ask_state["new_name_calls"] == 1
    assert store.load_meta("demo")["remote_url"] == str(source_a)
    assert store.load_meta("demo-2")["remote_url"] == str(source_b)
