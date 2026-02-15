from __future__ import annotations

from pathlib import Path

from skillchef import store
from skillchef.commands import init_cmd


def _mock_init_prompts(monkeypatch, confirm_defaults: list[bool]) -> None:
    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [])
    monkeypatch.setattr(init_cmd, "discover_editor_suggestions", lambda: [])
    monkeypatch.setattr("skillchef.ui.banner", lambda: None)
    monkeypatch.setattr("skillchef.ui.info", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.success", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.warn", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.show_platforms", lambda _p: None)
    monkeypatch.setattr("skillchef.ui.show_detected_keys", lambda _k: None)
    monkeypatch.setattr("skillchef.ui.show_config_summary", lambda _cfg: None)
    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])

    def choose(prompt: str, choices: list[str]) -> str:
        if "Default scope" in prompt:
            return "global"
        return choices[0]

    monkeypatch.setattr("skillchef.ui.choose", choose)
    monkeypatch.setattr(
        "skillchef.ui.ask",
        lambda prompt, default="": "vim" if "Preferred editor" in prompt else default,
    )

    def confirm(prompt: str, default: bool = False) -> bool:
        if "Run the onboarding wizard now?" in prompt:
            confirm_defaults.append(default)
            return False
        return False

    monkeypatch.setattr("skillchef.ui.confirm", confirm)


def test_init_wizard_prompt_default_depends_on_existing_skills(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    cases = [
        (False, True),
        (True, False),
    ]
    for has_existing_skills, expected_default in cases:
        confirm_defaults: list[bool] = []
        _mock_init_prompts(monkeypatch, confirm_defaults)
        if has_existing_skills:
            fetched = tmp_path / "seed-skill"
            fetched.mkdir(parents=True, exist_ok=True)
            (fetched / "SKILL.md").write_text("---\nname: demo\n---\n\n# Demo\n")
            store.cook("demo", fetched, str(fetched), "local", ["codex"])
        init_cmd.run(run_wizard=None)
        assert confirm_defaults == [expected_default]
        if has_existing_skills:
            store.remove("demo")


def test_run_wizard_chat_requires_key(monkeypatch) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [])
    monkeypatch.setattr("skillchef.ui.warn", lambda msg: warnings.append(msg))

    init_cmd._run_wizard_chat(
        step_number=2,
        step_title="Add local flavor",
        step_context="ctx",
    )

    assert warnings == ["No LLM key detected. Set one in your environment to use `chat`."]


def test_run_wizard_chat_calls_llm(monkeypatch) -> None:
    captured: dict[str, str] = {}
    printed: list[str] = []

    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [("OPENAI_API_KEY", "OpenAI")])
    monkeypatch.setattr("skillchef.ui.ask", lambda _prompt: "Why this step?")
    monkeypatch.setattr(
        init_cmd,
        "wizard_chat",
        lambda question, **kwargs: (
            captured.update(
                {
                    "question": question,
                    "step_label": str(kwargs.get("step_label", "")),
                    "project_context": str(kwargs.get("project_context", "")),
                }
            ),
            "Short answer",
        )[1],
    )
    monkeypatch.setattr("skillchef.ui.console.print", lambda msg="": printed.append(str(msg)))

    init_cmd._run_wizard_chat(
        step_number=2,
        step_title="Add local flavor",
        step_context="Adding local flavor instructions.",
        step_command="uvx skillchef flavor frontend-design",
        scope="global",
    )

    assert captured["question"] == "Why this step?"
    assert captured["step_label"] == "Step 2/3: Add local flavor"
    assert "Displayed command:" in captured["project_context"]
    assert "uvx skillchef flavor frontend-design" in captured["project_context"]
    assert any("Jeremy:" in line for line in printed)


def test_init_without_keys_skips_model_prompt(isolated_paths: dict[str, Path], monkeypatch) -> None:
    prompts: list[str] = []

    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [])
    monkeypatch.setattr(init_cmd, "discover_editor_suggestions", lambda: [])
    monkeypatch.setattr("skillchef.ui.banner", lambda: None)
    monkeypatch.setattr("skillchef.ui.info", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.success", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.warn", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.show_platforms", lambda _p: None)
    monkeypatch.setattr("skillchef.ui.show_detected_keys", lambda _k: None)
    monkeypatch.setattr("skillchef.ui.show_config_summary", lambda _cfg: None)
    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])
    monkeypatch.setattr("skillchef.ui.choose", lambda _p, _c: "global")

    def ask(prompt: str, default: str = "") -> str:
        prompts.append(prompt)
        if "Preferred editor" in prompt:
            return "vim"
        return default

    monkeypatch.setattr("skillchef.ui.ask", ask)

    init_cmd.run(scope="global", run_wizard=False)

    assert "AI model for semantic merge" not in prompts


def test_init_with_key_prompts_for_model(isolated_paths: dict[str, Path], monkeypatch) -> None:
    prompts: list[str] = []

    monkeypatch.setattr(init_cmd, "detect_keys", lambda: [("OPENAI_API_KEY", "OpenAI")])
    monkeypatch.setattr(init_cmd, "discover_editor_suggestions", lambda: [])
    monkeypatch.setattr("skillchef.ui.banner", lambda: None)
    monkeypatch.setattr("skillchef.ui.info", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.success", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.warn", lambda _msg: None)
    monkeypatch.setattr("skillchef.ui.show_platforms", lambda _p: None)
    monkeypatch.setattr("skillchef.ui.show_detected_keys", lambda _k: None)
    monkeypatch.setattr("skillchef.ui.show_config_summary", lambda _cfg: None)
    monkeypatch.setattr("skillchef.ui.multi_choose", lambda _p, _c: ["codex"])
    monkeypatch.setattr("skillchef.ui.choose", lambda _p, _c: "global")

    def ask(prompt: str, default: str = "") -> str:
        prompts.append(prompt)
        if "Preferred editor" in prompt:
            return "vim"
        if "AI model for semantic merge" in prompt:
            return "openai/gpt-5.2"
        return default

    monkeypatch.setattr("skillchef.ui.ask", ask)

    init_cmd.run(scope="global", run_wizard=False)

    assert "AI model for semantic merge" in prompts
