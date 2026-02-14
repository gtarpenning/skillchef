from __future__ import annotations

from pathlib import Path

import pytest

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
    assert meta["source_type"] == "http"
    assert meta["source_url"] == "https://example.com/hello"
    assert meta["source_path"] == "/hello"
    assert "source_repo" in meta
    assert "source_ref_requested" in meta
    assert "source_ref_resolved" in meta
    assert "source_commit_sha" in meta


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


def test_update_base_refreshes_source_metadata(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    fetched = _make_fetched_skill(tmp_path, body="v1")
    store.cook("hello-chef", fetched, "https://example.com/hello", "http", ["codex"])

    new_fetched = tmp_path / "fetched-new"
    new_fetched.mkdir()
    (new_fetched / "SKILL.md").write_text("---\nname: hello-chef\n---\n\n# Hello\n\nv2\n")

    monkeypatch.setattr(
        store.remote,
        "source_metadata",
        lambda _url, _type=None: {
            "source_type": "http",
            "source_url": "https://example.com/hello",
            "source_repo": "",
            "source_path": "/hello",
            "source_ref_requested": "",
            "source_ref_resolved": "etag-2",
            "source_commit_sha": "",
        },
    )

    store.update_base("hello-chef", new_fetched)
    meta = store.load_meta("hello-chef")

    assert meta["source_ref_resolved"] == "etag-2"


def test_scope_isolation_between_global_and_project(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    fetched = _make_fetched_skill(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)

    store.cook(
        "hello-chef", fetched, "https://example.com/global", "http", ["codex"], scope="global"
    )
    store.cook(
        "hello-chef", fetched, "https://example.com/project", "http", ["codex"], scope="project"
    )

    global_meta = store.load_meta("hello-chef", scope="global")
    project_meta = store.load_meta("hello-chef", scope="project")

    assert global_meta["remote_url"] == "https://example.com/global"
    assert project_meta["remote_url"] == "https://example.com/project"


def test_cook_refuses_to_overwrite_non_symlink_platform_path(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    fetched = _make_fetched_skill(tmp_path)
    conflict = isolated_paths["platform_codex"] / "hello-chef"
    conflict.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="Refusing to overwrite non-symlink"):
        store.cook("hello-chef", fetched, "local", "local", ["codex"])

    assert conflict.exists() and conflict.is_dir()


def test_remove_refuses_to_delete_non_symlink_platform_path(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    fetched = _make_fetched_skill(tmp_path)
    store.cook("hello-chef", fetched, "local", "local", ["codex"])

    link = isolated_paths["platform_codex"] / "hello-chef"
    link.unlink()
    link.mkdir()

    with pytest.raises(RuntimeError, match="Refusing to remove non-symlink"):
        store.remove("hello-chef")
