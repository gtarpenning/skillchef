from __future__ import annotations

from pathlib import Path

import pytest

from skillchef.commands import flavor_cmd


def test_run_no_skills_shows_info(monkeypatch) -> None:
    infos: list[str] = []
    monkeypatch.setattr(flavor_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(flavor_cmd, "ensure_config", lambda scope="auto": {"platforms": ["codex"]})
    monkeypatch.setattr(flavor_cmd.store, "list_skills", lambda scope="auto": [])
    monkeypatch.setattr(flavor_cmd.ui, "info", lambda msg: infos.append(msg))

    flavor_cmd.run(None)

    assert infos == ["No skills cooked yet."]


def test_run_waits_for_enter_before_rebuild(monkeypatch, tmp_path: Path) -> None:
    flavor_file = tmp_path / "flavor.md"
    calls: list[str] = []

    monkeypatch.setattr(flavor_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(flavor_cmd, "ensure_config", lambda scope="auto": {"platforms": ["codex"]})
    monkeypatch.setattr(flavor_cmd.store, "list_skills", lambda scope="auto": [{"name": "demo"}])
    monkeypatch.setattr(flavor_cmd.store, "flavor_path", lambda _name, scope="auto": flavor_file)
    monkeypatch.setattr(
        flavor_cmd.store,
        "live_skill_text",
        lambda _name, scope="auto": "before" if "rebuild" not in calls else "after",
    )
    monkeypatch.setattr(
        flavor_cmd,
        "open_editor",
        lambda _path, scope="auto": calls.append("open_editor"),
    )
    monkeypatch.setattr(
        flavor_cmd.ui,
        "ask",
        lambda _prompt, default="": calls.append("ask") or "",
    )
    monkeypatch.setattr(
        flavor_cmd.store,
        "rebuild_live",
        lambda _name, scope="auto": calls.append("rebuild"),
    )
    monkeypatch.setattr(flavor_cmd.merge, "diff_texts", lambda *_args: ["+after"])
    monkeypatch.setattr(flavor_cmd.ui, "show_diff", lambda _lines: calls.append("show_diff"))
    monkeypatch.setattr(flavor_cmd.ui, "success", lambda _msg: calls.append("success"))

    flavor_cmd.run("demo")

    assert flavor_file.read_text() == flavor_cmd.FLAVOR_TEMPLATE
    assert calls == ["open_editor", "ask", "rebuild", "show_diff", "success"]


def test_run_named_flavor_sets_active_and_edits_named_file(monkeypatch, tmp_path: Path) -> None:
    named = tmp_path / "flavors" / "project-a.md"
    calls: list[str] = []

    monkeypatch.setattr(flavor_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(flavor_cmd, "ensure_config", lambda scope="auto": {"platforms": ["codex"]})
    monkeypatch.setattr(flavor_cmd.store, "list_skills", lambda scope="auto": [{"name": "demo"}])
    monkeypatch.setattr(
        flavor_cmd.store,
        "set_active_flavor",
        lambda _name, _flavor, scope="auto": calls.append("set_active"),
    )
    monkeypatch.setattr(
        flavor_cmd.store,
        "named_flavor_path",
        lambda _name, _flavor, scope="auto": named,
    )
    monkeypatch.setattr(
        flavor_cmd.store,
        "live_skill_text",
        lambda _name, scope="auto": "before" if "rebuild" not in calls else "after",
    )
    monkeypatch.setattr(
        flavor_cmd, "open_editor", lambda _path, scope="auto": calls.append("open_editor")
    )
    monkeypatch.setattr(flavor_cmd.ui, "ask", lambda _prompt, default="": calls.append("ask") or "")
    monkeypatch.setattr(
        flavor_cmd.store,
        "rebuild_live",
        lambda _name, scope="auto": calls.append("rebuild"),
    )
    monkeypatch.setattr(flavor_cmd.merge, "diff_texts", lambda *_args: ["+after"])
    monkeypatch.setattr(flavor_cmd.ui, "show_diff", lambda _lines: calls.append("show_diff"))
    monkeypatch.setattr(flavor_cmd.ui, "success", lambda _msg: calls.append("success"))

    flavor_cmd.run("demo", flavor_name="project-a")

    assert named.read_text() == flavor_cmd.FLAVOR_TEMPLATE
    assert calls == ["set_active", "open_editor", "ask", "rebuild", "show_diff", "success"]


def test_run_use_switches_active_without_editor(monkeypatch) -> None:
    calls: list[str] = []
    successes: list[str] = []

    monkeypatch.setattr(flavor_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(flavor_cmd, "ensure_config", lambda scope="auto": {"platforms": ["codex"]})
    monkeypatch.setattr(flavor_cmd.store, "list_skills", lambda scope="auto": [{"name": "demo"}])
    monkeypatch.setattr(flavor_cmd.store, "validate_flavor_name", lambda name: name)
    monkeypatch.setattr(flavor_cmd.store, "flavor_exists", lambda _n, _f, scope="auto": True)
    monkeypatch.setattr(
        flavor_cmd.store,
        "live_skill_text",
        lambda _n, scope="auto": "before" if "rebuild" not in calls else "after",
    )
    monkeypatch.setattr(
        flavor_cmd.store,
        "set_active_flavor",
        lambda _n, _f, scope="auto": calls.append("set_active"),
    )
    monkeypatch.setattr(
        flavor_cmd.store,
        "rebuild_live",
        lambda _n, scope="auto": calls.append("rebuild"),
    )
    monkeypatch.setattr(flavor_cmd.merge, "diff_texts", lambda *_args: ["+after"])
    monkeypatch.setattr(flavor_cmd.ui, "show_diff", lambda _lines: calls.append("show_diff"))
    monkeypatch.setattr(flavor_cmd.ui, "success", lambda msg: successes.append(msg))
    monkeypatch.setattr(
        flavor_cmd,
        "open_editor",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not edit")),
    )

    flavor_cmd.run("demo", use_flavor="project-a")

    assert calls == ["set_active", "rebuild", "show_diff"]
    assert "project-a" in successes[0]


def test_run_use_missing_flavor_errors(monkeypatch) -> None:
    errors: list[str] = []

    monkeypatch.setattr(flavor_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(flavor_cmd, "ensure_config", lambda scope="auto": {"platforms": ["codex"]})
    monkeypatch.setattr(flavor_cmd.store, "list_skills", lambda scope="auto": [{"name": "demo"}])
    monkeypatch.setattr(flavor_cmd.store, "validate_flavor_name", lambda name: name)
    monkeypatch.setattr(flavor_cmd.store, "flavor_exists", lambda _n, _f, scope="auto": False)
    monkeypatch.setattr(
        flavor_cmd.store, "list_flavor_names", lambda _n, scope="auto": ["default", "project-a"]
    )
    monkeypatch.setattr(flavor_cmd.ui, "error", lambda msg: errors.append(msg))

    with pytest.raises(SystemExit):
        flavor_cmd.run("demo", use_flavor="missing")

    assert errors and "does not exist" in errors[0]
