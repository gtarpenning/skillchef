from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from skillchef import config, merge, remote, store, ui
from skillchef.commands import sync_cmd
from skillchef.commands.common import cleanup_fetched, open_editor
from skillchef.llm import detect_keys, wizard_chat

README_EXAMPLE_SOURCE = (
    "https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md"
)
WIZARD_UPSTREAM_ROOT = "wizard-upstreams"
WIZARD_UPDATE_MARKER = "Wizard sync demo update"
WIZARD_FLAVOR_TEXT = (
    "Prefer practical examples and add one short checklist at the end of each section.\n"
)
WIZARD_TOTAL_STEPS = 3


def maybe_run_example_wizard(
    cfg: dict[str, object],
    *,
    scope: str,
    run_example_wizard_fn: Callable[..., None] | None = None,
) -> None:
    ui.console.print()
    recommend = len(store.list_skills(scope=scope)) == 0
    prompt = "Run the onboarding wizard now? (cook -> flavor -> sync)"
    if recommend:
        prompt += " [recommended]"
    if not ui.confirm(prompt, default=recommend):
        return

    runner = run_example_wizard_fn or run_example_wizard
    runner(cfg, scope=scope)


def run_example_wizard(
    cfg: dict[str, object],
    *,
    scope: str,
    fetch_fn=remote.fetch,
    chat_macro_fn: Callable[..., None] | None = None,
) -> None:
    chat_runner = chat_macro_fn or run_wizard_chat
    ui.wizard_message(
        "Onboarding Wizard",
        (
            "Hello! I am chef Jeremy, your onboarding wizard-chef!\n\n"
            "I will walk you through a real skill workflow:\n"
            "cook -> flavor -> sync.\n\n"
            "We will use Anthropics `frontend-design` skill and simulate an upstream update\n"
            "so you can see flavor-preserving sync behavior end to end.\n\n"
            "At any time type `chat` to ask Jeremy any questions you might have."
        ),
    )
    ui.console.print()

    step_1_title = "Fetch and stage upstream skill"
    step_1_body = (
        "Pulling the example `frontend-design` skill from the README source.\n\n"
        "This creates a local upstream snapshot that we can later modify to simulate a remote update."
    )
    ui.wizard_step(1, WIZARD_TOTAL_STEPS, step_1_title, step_1_body)
    step_1_command = f"uvx skillchef cook {README_EXAMPLE_SOURCE}"
    ui.require_exact_command(
        step_1_command,
        macros={
            "chat": lambda: chat_runner(
                step_number=1,
                step_title=step_1_title,
                step_context=step_1_body,
                step_command=step_1_command,
                scope=scope,
            )
        },
    )
    fetched_dir, _ = fetch_fn(README_EXAMPLE_SOURCE)
    try:
        skill_name = _skill_name_from_file(fetched_dir / "SKILL.md")
        upstream_dir = _prepare_wizard_upstream(skill_name, fetched_dir, scope=scope)
    finally:
        cleanup_fetched(fetched_dir)

    platforms = _platforms_from_cfg(cfg)
    if not platforms:
        ui.warn("No platforms selected in config; skipping onboarding wizard.")
        return

    if not _cook_example_skill(skill_name, upstream_dir, platforms=platforms, scope=scope):
        return

    step_2_title = "Add local flavor"
    step_2_body = (
        "Adding local flavor instructions.\n\n"
        "These instructions represent your preferences and should survive future sync updates."
    )
    ui.wizard_step(2, WIZARD_TOTAL_STEPS, step_2_title, step_2_body)
    step_2_command = f"uvx skillchef flavor {skill_name}"
    ui.require_exact_command(
        step_2_command,
        macros={
            "chat": lambda: chat_runner(
                step_number=2,
                step_title=step_2_title,
                step_context=step_2_body,
                step_command=step_2_command,
                scope=scope,
            )
        },
    )
    _apply_example_flavor(skill_name, scope=scope)

    _simulate_upstream_update(upstream_dir / "SKILL.md")

    step_3_title = "Sync and preserve flavor"
    step_3_body = (
        "Running sync so the local flavor remains effective after the upstream update.\n\n"
        "You can inspect the resulting live skill to confirm the merge behavior."
    )
    ui.wizard_step(3, WIZARD_TOTAL_STEPS, step_3_title, step_3_body)
    step_3_command = f"uvx skillchef sync {skill_name} --no-ai"
    ui.require_exact_command(
        step_3_command,
        macros={
            "chat": lambda: chat_runner(
                step_number=3,
                step_title=step_3_title,
                step_context=step_3_body,
                step_command=step_3_command,
                scope=scope,
            )
        },
    )
    sync_cmd.run(skill_name, no_ai=True, scope=scope)
    ui.success(f"Onboarding wizard complete for [bold]{skill_name}[/bold].")


def run_wizard_chat(
    *,
    step_number: int,
    step_title: str,
    step_context: str,
    step_command: str | None = None,
    scope: str = "auto",
    detect_keys_fn=detect_keys,
    wizard_chat_fn=wizard_chat,
) -> None:
    if not detect_keys_fn():
        ui.warn("No LLM key detected. Set one in your environment to use `chat`.")
        return

    question = ui.ask("Ask Jeremy")
    if not question.strip():
        ui.warn("Please enter a question before using `chat`.")
        return

    step_label = f"Step {step_number}/{WIZARD_TOTAL_STEPS}: {step_title}"
    project_context = "Wizard flow: cook -> flavor -> sync."
    if step_command:
        project_context += f"\nDisplayed command:\n{step_command}"
    project_context += f"\nScope: {scope}"
    try:
        answer = wizard_chat_fn(
            question,
            step_label=step_label,
            step_context=step_context,
            project_context=project_context,
            scope=scope,
        )
    except Exception as exc:
        ui.warn(f"Chat unavailable: {exc}")
        return

    ui.console.print()
    ui.console.print(f"[cyan]Jeremy:[/cyan] {answer}")
    ui.console.print()


def _platforms_from_cfg(cfg: dict[str, object]) -> list[str]:
    raw = cfg.get("platforms")
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if str(p) in config.PLATFORMS]


def _skill_name_from_file(skill_md: Path) -> str:
    if not skill_md.exists():
        return "frontend-design"
    text = skill_md.read_text()
    front, _ = merge.split_frontmatter(text)
    if "name:" in front:
        for line in front.splitlines():
            if line.strip().startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"').strip("'")
                if name:
                    return name
    return "frontend-design"


def _prepare_wizard_upstream(skill_name: str, fetched_dir: Path, *, scope: str) -> Path:
    upstream_root = config.scope_home(scope=scope) / WIZARD_UPSTREAM_ROOT
    upstream_root.mkdir(parents=True, exist_ok=True)
    upstream_dir = upstream_root / skill_name
    if upstream_dir.exists():
        shutil.rmtree(upstream_dir)
    shutil.copytree(fetched_dir, upstream_dir)
    return upstream_dir


def _cook_example_skill(
    skill_name: str,
    upstream_dir: Path,
    *,
    platforms: list[str],
    scope: str,
) -> bool:
    if store.skill_dir(skill_name, scope=scope).exists():
        action = ui.choose(
            f"Example skill '{skill_name}' already exists. How should the onboarding wizard proceed?",
            ["overwrite", "skip wizard"],
        )
        if action == "skip wizard":
            ui.info("Onboarding wizard skipped.")
            return False
    store.cook(skill_name, upstream_dir, str(upstream_dir), "local", platforms, scope=scope)
    ui.success(f"Cooked example skill [bold]{skill_name}[/bold].")
    return True


def _apply_example_flavor(skill_name: str, *, scope: str) -> None:
    flavor_md = store.flavor_path(skill_name, scope=scope)
    if not flavor_md.exists() or not flavor_md.read_text().strip():
        flavor_md.write_text(WIZARD_FLAVOR_TEXT)
    if ui.confirm("Open your editor to tweak this flavor now?", default=False):
        open_editor(flavor_md, scope=scope)
    old_live = store.live_skill_text(skill_name, scope=scope)
    store.rebuild_live(skill_name, scope=scope)
    new_live = store.live_skill_text(skill_name, scope=scope)
    ui.show_diff(merge.diff_texts(old_live, new_live, "before flavor", "after flavor"))
    ui.success("Local flavor saved.")


def _simulate_upstream_update(skill_md: Path) -> None:
    text = skill_md.read_text() if skill_md.exists() else ""
    if WIZARD_UPDATE_MARKER in text:
        return
    front, body = merge.split_frontmatter(text)
    body = body.rstrip()
    if body:
        body += "\n\n"
    body += f"## Wizard sync demo update\n\n{WIZARD_UPDATE_MARKER}: upstream content changed.\n"
    skill_md.write_text(front + body + "\n")
