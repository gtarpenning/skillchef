from __future__ import annotations

from pathlib import Path

import pytest

from skillchef import store
from skillchef.commands import cook_cmd


def test_resolve_source_for_cook_local_single_candidate(tmp_path: Path) -> None:
    src = tmp_path / "skills" / "hello"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("hello")

    resolved = cook_cmd._resolve_source_for_cook(str(tmp_path / "skills"))

    assert resolved == str(src)


def test_resolve_source_for_cook_local_multiple_candidates_uses_selector(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "skills"
    a = root / "a"
    b = root / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "SKILL.md").write_text("a")
    (b / "SKILL.md").write_text("b")

    monkeypatch.setattr(cook_cmd.ui, "choose", lambda _p, choices: choices[1])

    resolved = cook_cmd._resolve_source_for_cook(str(root))

    assert resolved == str(b)


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
