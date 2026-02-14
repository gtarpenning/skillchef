from __future__ import annotations

from pathlib import Path

from skillchef import store


def _make_fetched_skill(tmp_path: Path, *, body: str = "Base body") -> Path:
    fetched = tmp_path / "fetched"
    fetched.mkdir()
    (fetched / "SKILL.md").write_text(f"---\nname: hello-chef\n---\n\n# Hello\n\n{body}\n")
    (fetched / "scripts").mkdir()
    (fetched / "scripts" / "tool.py").write_text("print('ok')\n")
    return fetched


def test_cook_creates_expected_layout_meta_and_symlink(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    fetched = _make_fetched_skill(tmp_path)

    skill_dir = store.cook(
        "hello-chef",
        fetched,
        "https://example.com/hello",
        "http",
        ["codex"],
    )

    base = skill_dir / "base"
    live = skill_dir / "live"
    meta = store.load_meta("hello-chef")
    link = isolated_paths["platform_codex"] / "hello-chef"

    assert base.exists() and live.exists()
    assert (base / "SKILL.md").exists() and (live / "SKILL.md").exists()
    assert meta["name"] == "hello-chef"
    assert meta["remote_type"] == "http"
    assert meta["platforms"] == ["codex"]
    assert meta["base_sha256"] == store.hash_dir(base)
    assert link.is_symlink()
    assert link.resolve() == live.resolve()


def test_rebuild_live_reapplies_flavor_without_changing_base(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    fetched = _make_fetched_skill(tmp_path, body="Original")
    store.cook("hello-chef", fetched, "local", "local", ["codex"])

    flavor = store.flavor_path("hello-chef")
    flavor.write_text("Keep local behavior\n")

    old_base = store.base_skill_text("hello-chef")
    store.rebuild_live("hello-chef")

    assert store.base_skill_text("hello-chef") == old_base
    live = store.live_skill_text("hello-chef")
    assert "## Local Flavor" in live
    assert "Keep local behavior" in live
    assert live.index("Original") < live.index("## Local Flavor")


def test_hash_dir_is_stable_across_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    (first / "b.txt").write_text("B")
    (first / "a.txt").write_text("A")

    (second / "a.txt").write_text("A")
    (second / "b.txt").write_text("B")

    assert store.hash_dir(first) == store.hash_dir(second)


def test_remove_deletes_store_dir_and_platform_symlink(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    fetched = _make_fetched_skill(tmp_path)
    store.cook("hello-chef", fetched, "local", "local", ["codex"])

    skill_path = store.skill_dir("hello-chef")
    link = isolated_paths["platform_codex"] / "hello-chef"
    assert skill_path.exists() and link.exists()

    store.remove("hello-chef")

    assert not skill_path.exists()
    assert not link.exists()
