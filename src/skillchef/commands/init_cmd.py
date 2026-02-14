from __future__ import annotations

import os

from skillchef import config, remote, ui, wizard
from skillchef.llm import default_model_for_key, detect_keys, wizard_chat

from .common import discover_editor_suggestions

README_EXAMPLE_SOURCE = wizard.README_EXAMPLE_SOURCE
WIZARD_UPSTREAM_ROOT = wizard.WIZARD_UPSTREAM_ROOT
WIZARD_UPDATE_MARKER = wizard.WIZARD_UPDATE_MARKER
WIZARD_FLAVOR_TEXT = wizard.WIZARD_FLAVOR_TEXT
WIZARD_TOTAL_STEPS = wizard.WIZARD_TOTAL_STEPS


def run(scope: str = "auto", run_wizard: bool | None = None) -> None:
    ui.banner()
    ui.console.print()

    ui.info("Scanning for agent platforms...\n")
    ui.show_platforms(config.PLATFORMS)
    ui.console.print()

    detected = detect_keys()
    ui.show_detected_keys(detected)
    ui.console.print()

    platforms = ui.multi_choose(
        "Which platforms do you use?",
        list(config.PLATFORMS.keys()),
    )
    default_scope = ui.choose("Default scope for skill storage", ["global", "project"])

    selected_key_env = ""
    provider = ""
    if detected:
        if len(detected) == 1:
            selected_key_env, provider = detected[0]
        else:
            label_to_env = {f"{provider} ({env_var})": env_var for env_var, provider in detected}
            key_choices = list(label_to_env.keys())
            selected_label = ui.choose(
                "Multiple LLM keys found. Which key should AI merge use?", key_choices
            )
            selected_key_env = label_to_env[selected_label]
            provider = next(p for env_var, p in detected if env_var == selected_key_env)
        ui.info(f"AI merge will use [bold]{selected_key_env}[/bold] ({provider})")
    ui.console.print()

    default_editor = os.environ.get("EDITOR", "vim")
    suggestions = discover_editor_suggestions()
    if suggestions:
        display_to_cmd = {f"{label} ({cmd})": cmd for label, cmd in suggestions}
        editor_choices = list(display_to_cmd.keys()) + ["Custom value"]
        selected_editor = ui.choose("Preferred editor", editor_choices)
        editor = (
            display_to_cmd[selected_editor]
            if selected_editor in display_to_cmd
            else ui.ask(
                "Preferred editor",
                default=default_editor,
            )
        )
    else:
        editor = ui.ask("Preferred editor", default=default_editor)

    default_model = default_model_for_key(selected_key_env)
    model = ui.ask("AI model for semantic merge", default=default_model)

    cfg = {
        "platforms": platforms,
        "editor": editor,
        "model": model,
        "llm_api_key_env": selected_key_env,
        "default_scope": default_scope,
    }
    config.save(cfg, scope=scope)

    ui.console.print()
    ui.show_config_summary(cfg)
    ui.console.print()
    ui.success(f"Config saved to [bold]{config.config_file_path(scope=scope)}[/bold]")
    if run_wizard is True:
        try:
            run_example_wizard(cfg, scope=scope)
        except Exception as e:
            ui.warn(f"Onboarding wizard failed: {e}")
    elif run_wizard is None:
        _maybe_run_example_wizard(cfg, scope=scope)


def _maybe_run_example_wizard(cfg: dict[str, object], *, scope: str) -> None:
    try:
        wizard.maybe_run_example_wizard(cfg, scope=scope, run_example_wizard_fn=run_example_wizard)
    except Exception as e:
        ui.warn(f"Onboarding wizard failed: {e}")


def run_example_wizard(cfg: dict[str, object], *, scope: str) -> None:
    wizard.run_example_wizard(
        cfg,
        scope=scope,
        fetch_fn=remote.fetch,
        chat_macro_fn=_run_wizard_chat,
    )


def _run_wizard_chat(
    *,
    step_number: int,
    step_title: str,
    step_context: str,
    step_command: str | None = None,
    scope: str = "auto",
) -> None:
    wizard.run_wizard_chat(
        step_number=step_number,
        step_title=step_title,
        step_context=step_context,
        step_command=step_command,
        scope=scope,
        detect_keys_fn=detect_keys,
        wizard_chat_fn=wizard_chat,
    )
