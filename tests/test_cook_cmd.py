from __future__ import annotations

from pathlib import Path

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
