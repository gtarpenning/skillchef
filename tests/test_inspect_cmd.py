from __future__ import annotations

import pytest

from skillchef.commands import inspect_cmd


def test_run_shows_inspect_and_live_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    metas = [
        {
            "name": "hello-chef",
            "remote_url": "https://example.com/hello",
            "remote_type": "http",
            "platforms": ["codex"],
        }
    ]

    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": metas)
    monkeypatch.setattr(inspect_cmd.store, "has_flavor", lambda _n, scope="auto": True)
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_inspect",
        lambda meta, flavored=False: shown.append(str(meta["name"])),
    )
    monkeypatch.setattr(
        inspect_cmd.store, "live_skill_text", lambda _n, scope="auto": "# hello-chef\n"
    )
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_md",
        lambda text, title="SKILL.md": shown.append(f"{title}:{text}"),
    )

    inspect_cmd.run("hello-chef")

    assert shown[0] == "hello-chef"
    assert shown[1].startswith("hello-chef/live/SKILL.md:")


def test_run_errors_when_skill_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    errors: list[str] = []
    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": [])
    monkeypatch.setattr(inspect_cmd.ui, "error", lambda msg: errors.append(msg))

    with pytest.raises(SystemExit):
        inspect_cmd.run("missing")

    assert errors and "not found" in errors[0]


def test_run_without_name_prompts_and_inspects_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    metas = [
        {
            "name": "hello-chef",
            "remote_url": "https://example.com/hello",
            "remote_type": "http",
            "platforms": ["codex"],
        }
    ]

    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": metas)
    monkeypatch.setattr(inspect_cmd.ui, "choose_optional", lambda _prompt, _choices: "hello-chef")
    monkeypatch.setattr(inspect_cmd.store, "has_flavor", lambda _n, scope="auto": False)
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_inspect",
        lambda meta, flavored=False: shown.append(str(meta["name"])),
    )
    monkeypatch.setattr(
        inspect_cmd.store, "live_skill_text", lambda _n, scope="auto": "# hello-chef\n"
    )
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_md",
        lambda text, title="SKILL.md": shown.append(f"{title}:{text}"),
    )

    inspect_cmd.run(None)

    assert shown[0] == "hello-chef"
    assert shown[1].startswith("hello-chef/live/SKILL.md:")


def test_run_without_name_returns_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"shown": 0}
    metas = [{"name": "hello-chef"}]

    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": metas)
    monkeypatch.setattr(inspect_cmd.ui, "choose_optional", lambda _prompt, _choices: None)
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_inspect",
        lambda _meta, flavored=False: calls.__setitem__("shown", calls["shown"] + 1),
    )

    inspect_cmd.run(None)

    assert calls["shown"] == 0


def test_run_truncates_preview_and_can_show_full(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    lines = [f"line {i}" for i in range(1, 61)]
    full_text = "\n".join(lines) + "\n"
    metas = [{"name": "hello-chef"}]
    actions = iter(["see full skill?", "done"])

    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.ui, "can_use_interactive_selector", lambda: True)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": metas)
    monkeypatch.setattr(inspect_cmd.store, "has_flavor", lambda _n, scope="auto": False)
    monkeypatch.setattr(inspect_cmd.ui, "choose_optional", lambda _prompt, _choices: next(actions))
    monkeypatch.setattr(
        inspect_cmd.ui, "show_skill_inspect", lambda _meta, flavored=False: shown.append("meta")
    )
    monkeypatch.setattr(inspect_cmd.store, "live_skill_text", lambda _n, scope="auto": full_text)
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_md",
        lambda text, title="SKILL.md": shown.append(f"{title}:{text}"),
    )
    monkeypatch.setattr(inspect_cmd.ui, "info", lambda _msg: None)

    inspect_cmd.run("hello-chef")

    assert shown[0] == "meta"
    assert "... [truncated]" in shown[1]
    assert "line 60" not in shown[1]
    assert "line 60" in shown[2]


def test_run_menu_actions_open_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    metas = [{"name": "hello-chef"}]
    actions = iter(["open skill in finder", "open in editor", "done"])

    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.ui, "can_use_interactive_selector", lambda: True)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": metas)
    monkeypatch.setattr(inspect_cmd.store, "has_flavor", lambda _n, scope="auto": False)
    monkeypatch.setattr(inspect_cmd.ui, "choose_optional", lambda _prompt, _choices: next(actions))
    monkeypatch.setattr(inspect_cmd.ui, "show_skill_inspect", lambda _meta, flavored=False: None)
    monkeypatch.setattr(
        inspect_cmd.store, "live_skill_text", lambda _n, scope="auto": "# hello-chef\n"
    )
    monkeypatch.setattr(inspect_cmd.ui, "show_skill_md", lambda text, title="SKILL.md": None)
    monkeypatch.setattr(inspect_cmd, "open_in_file_manager", lambda p: opened.append(str(p)))
    monkeypatch.setattr(
        inspect_cmd,
        "open_editor",
        lambda p, scope="auto": opened.append(str(p)),
    )

    inspect_cmd.run("hello-chef")

    assert len(opened) == 2
    assert opened[0].endswith("hello-chef/live/SKILL.md")
    assert opened[1].endswith("hello-chef/live/SKILL.md")
