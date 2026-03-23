from __future__ import annotations

from pathlib import Path

import pytest

from skillchef import store
from skillchef.commands import cook_cmd


def test_resolve_sources_for_cook_local_single_candidate(tmp_path: Path) -> None:
    src = tmp_path / "skills" / "hello"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("hello")

    resolved = cook_cmd._resolve_sources_for_cook(str(tmp_path / "skills"))

    assert resolved == [str(src)]


def test_resolve_sources_for_cook_local_multiple_candidates_use_multi_select(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "skills"
    a = root / "a"
    b = root / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "SKILL.md").write_text("a")
    (b / "SKILL.md").write_text("b")

    monkeypatch.setattr(cook_cmd.ui, "multi_choose", lambda _p, choices: [choices[0], choices[1]])

    resolved = cook_cmd._resolve_sources_for_cook(str(root))

    assert resolved == [str(a), str(b)]


def test_resolve_sources_for_cook_local_multiple_candidates_requires_selection(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "skills"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "SKILL.md").write_text("a")
    (root / "b" / "SKILL.md").write_text("b")

    monkeypatch.setattr(cook_cmd.ui, "multi_choose", lambda _p, _choices: [])
    monkeypatch.setattr(cook_cmd.ui, "info", lambda _msg: None)

    with pytest.raises(SystemExit):
        cook_cmd._resolve_sources_for_cook(str(root))


def test_resolve_fetched_skills_multiple_candidates_requires_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fetched_root = tmp_path / "fetched"
    (fetched_root / "alpha").mkdir(parents=True)
    (fetched_root / "beta").mkdir(parents=True)
    (fetched_root / "alpha" / "SKILL.md").write_text("a")
    (fetched_root / "beta" / "SKILL.md").write_text("b")

    monkeypatch.setattr(cook_cmd.ui, "multi_choose", lambda _p, _choices: [])
    monkeypatch.setattr(cook_cmd.ui, "info", lambda _msg: None)

    with pytest.raises(SystemExit):
        cook_cmd._resolve_fetched_skills(
            fetched_root,
            source="https://github.com/acme/repo/tree/main/skills",
            remote_type="github",
        )


def test_resolve_existing_name_non_interactive_requires_force(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = store.skill_dir("hello-chef")
    existing.mkdir(parents=True)

    monkeypatch.setattr(cook_cmd.ui, "can_use_interactive_selector", lambda: False)

    with pytest.raises(SystemExit):
        cook_cmd._resolve_existing_name("hello-chef", force_overwrite=False)


def test_resolve_existing_name_force_overwrite(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = store.skill_dir("hello-chef")
    existing.mkdir(parents=True)
    monkeypatch.setattr(cook_cmd.ui, "can_use_interactive_selector", lambda: False)

    assert cook_cmd._resolve_existing_name("hello-chef", force_overwrite=True) == "hello-chef"


def test_resolve_existing_name_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "existing").mkdir()
    monkeypatch.setattr(cook_cmd.store, "skill_dir", lambda n, scope="auto": tmp_path / n)
    monkeypatch.setattr(cook_cmd.ui, "can_use_interactive_selector", lambda: True)
    monkeypatch.setattr(cook_cmd.ui, "choose", lambda _p, _c: "rename")
    monkeypatch.setattr(cook_cmd.ui, "ask", lambda _p, default="": "renamed")

    assert cook_cmd._resolve_existing_name("existing", force_overwrite=False) == "renamed"


def test_backup_existing_skill_moves_directory(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    src = store.skill_dir("hello-chef")
    (src / "base").mkdir(parents=True)
    (src / "base" / "SKILL.md").write_text("x")

    infos: list[str] = []
    monkeypatch.setattr(cook_cmd.ui, "info", lambda msg: infos.append(msg))

    backup_path = cook_cmd._backup_existing_skill("hello-chef")

    assert not src.exists()
    assert backup_path.exists()
    assert (backup_path / "base" / "SKILL.md").exists()
    assert infos


def test_run_reports_partial_failures_for_multi_skill_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fetched_root = tmp_path / "fetched"
    alpha = fetched_root / "alpha"
    beta = fetched_root / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "SKILL.md").write_text("---\nname: alpha\n---\n")
    (beta / "SKILL.md").write_text("---\nname: beta\n---\n")

    errors: list[str] = []
    cooked: list[tuple[str, str]] = []

    monkeypatch.setattr(cook_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(cook_cmd.ui, "multi_choose", lambda _p, choices: list(choices))
    monkeypatch.setattr(cook_cmd.ui, "ask", lambda _p, default="": default)
    monkeypatch.setattr(cook_cmd.ui, "info", lambda _msg: None)
    monkeypatch.setattr(cook_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(cook_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(cook_cmd.ui, "error", lambda msg: errors.append(msg))
    monkeypatch.setattr(cook_cmd, "ensure_config", lambda scope="auto": {"platforms": ["codex"]})
    monkeypatch.setattr(cook_cmd, "cleanup_fetched", lambda _path: None)
    monkeypatch.setattr(cook_cmd.remote, "fetch", lambda _source: (fetched_root, "github"))
    monkeypatch.setattr(
        cook_cmd,
        "_resolve_sources_for_cook",
        lambda _source: ["https://github.com/acme/repo/tree/main/skills"],
    )
    monkeypatch.setattr(cook_cmd, "_resolve_existing_name", lambda name, **_kwargs: name)

    def fake_store_cook(name: str, _dir: Path, skill_source: str, *_args, **_kwargs) -> None:
        if name == "beta":
            raise RuntimeError("boom")
        cooked.append((name, skill_source))

    monkeypatch.setattr(cook_cmd.store, "cook", fake_store_cook)

    with pytest.raises(SystemExit):
        cook_cmd.run("https://github.com/acme/repo/tree/main/skills")

    assert cooked == [("alpha", "https://github.com/acme/repo/tree/main/skills/alpha")]
    assert any("https://github.com/acme/repo/tree/main/skills/beta: boom" in msg for msg in errors)
    assert any("Cook completed with 1 failure." in msg for msg in errors)
