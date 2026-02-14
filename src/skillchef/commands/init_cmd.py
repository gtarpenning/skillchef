from __future__ import annotations

import os

from skillchef import config, ui
from skillchef.llm import default_model_for_key, detect_keys

from .common import discover_editor_suggestions


def run() -> None:
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
    }
    config.save(cfg)

    ui.console.print()
    ui.show_config_summary(cfg)
    ui.console.print()
    ui.success(f"Config saved to [bold]{config.CONFIG_PATH}[/bold]")
