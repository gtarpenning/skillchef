from __future__ import annotations

from pathlib import Path

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

    assert flavor_file.read_text() == "# Add your local flavor below\n\n"
    assert calls == ["open_editor", "ask", "rebuild", "show_diff", "success"]
