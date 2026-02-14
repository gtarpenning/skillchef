from __future__ import annotations

import pytest

from skillchef.commands import inspect_cmd


def _meta(name: str = "hello-chef") -> dict[str, str]:
    return {
        "name": name,
        "remote_url": "https://example.com/hello",
        "remote_type": "http",
    }


def test_run_selection_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.store, "has_flavor", lambda _n, scope="auto": False)
    monkeypatch.setattr(
        inspect_cmd.store, "live_skill_text", lambda _n, scope="auto": "# hello-chef\n"
    )

    shown: list[str] = []
    monkeypatch.setattr(
        inspect_cmd.ui,
        "show_skill_inspect",
        lambda meta, flavored=False: shown.append(str(meta["name"])),
    )
    monkeypatch.setattr(
        inspect_cmd.ui, "show_skill_md", lambda _text, title="SKILL.md": shown.append(title)
    )
    monkeypatch.setattr(inspect_cmd.ui, "can_use_interactive_selector", lambda: False)

    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": [_meta()])
    inspect_cmd.run("hello-chef")
    assert shown == ["hello-chef", "hello-chef/live/SKILL.md"]

    shown.clear()
    monkeypatch.setattr(inspect_cmd.ui, "choose_optional", lambda _prompt, _choices: "hello-chef")
    inspect_cmd.run(None)
    assert shown == ["hello-chef", "hello-chef/live/SKILL.md"]

    shown.clear()
    monkeypatch.setattr(inspect_cmd.ui, "choose_optional", lambda _prompt, _choices: None)
    inspect_cmd.run(None)
    assert shown == []

    errors: list[str] = []
    monkeypatch.setattr(inspect_cmd.ui, "error", lambda msg: errors.append(msg))
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": [])
    with pytest.raises(SystemExit):
        inspect_cmd.run("missing")
    assert errors and "not found" in errors[0]


def test_run_interactive_preview_and_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    opened: list[str] = []
    lines = [f"line {i}" for i in range(1, 61)]
    full_text = "\n".join(lines) + "\n"
    actions = iter(["see full skill?", "open skill in finder", "open in editor", "done"])

    monkeypatch.setattr(inspect_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(inspect_cmd.ui, "can_use_interactive_selector", lambda: True)
    monkeypatch.setattr(inspect_cmd.store, "list_skills", lambda scope="auto": [_meta()])
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
    monkeypatch.setattr(inspect_cmd, "open_in_file_manager", lambda p: opened.append(str(p)))
    monkeypatch.setattr(inspect_cmd, "open_editor", lambda p, scope="auto": opened.append(str(p)))

    inspect_cmd.run("hello-chef")

    assert shown[0] == "meta"
    assert "... [truncated]" in shown[1]
    assert "line 60" not in shown[1]
    assert "line 60" in shown[2]
    assert len(opened) == 2
    assert opened[0].endswith("hello-chef/live/SKILL.md")
    assert opened[1].endswith("hello-chef/live/SKILL.md")
