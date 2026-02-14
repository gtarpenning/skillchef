from __future__ import annotations

from skillchef.commands import list_cmd


def test_run_prints_table_and_skips_viewer_when_non_interactive(monkeypatch) -> None:
    skills = [{"name": "hello-chef", "remote_url": "https://example.com/hello"}]
    calls: dict[str, int] = {"table": 0, "viewer": 0}

    monkeypatch.setattr(list_cmd.store, "list_skills", lambda scope="auto": skills)
    monkeypatch.setattr(list_cmd.store, "has_flavor", lambda _n, scope="auto": False)
    monkeypatch.setattr(list_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(
        list_cmd.ui,
        "skill_table",
        lambda _skills, has_flavor_fn=None: calls.__setitem__("table", calls["table"] + 1),
    )
    monkeypatch.setattr(list_cmd.ui, "can_use_interactive_selector", lambda: False)
    monkeypatch.setattr(
        list_cmd,
        "_run_viewer",
        lambda _skills, scope="auto": calls.__setitem__("viewer", calls["viewer"] + 1),
    )

    list_cmd.run()

    assert calls["table"] == 1
    assert calls["viewer"] == 0


def test_run_viewer_shows_selected_skill_until_exit(monkeypatch) -> None:
    skills = [{"name": "hello-chef", "remote_url": "https://example.com/hello"}]
    inspected: list[str] = []

    selections = iter(["hello-chef", None])

    monkeypatch.setattr(list_cmd.ui, "choose_optional", lambda _p, _c: next(selections))
    monkeypatch.setattr(list_cmd.ui, "info", lambda _m: None)
    monkeypatch.setattr(
        list_cmd.inspect_cmd,
        "inspect_skill_from_meta",
        lambda meta, scope="auto": inspected.append(str(meta["name"])),
    )

    list_cmd._run_viewer(skills)

    assert inspected == ["hello-chef"]
