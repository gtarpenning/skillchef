from __future__ import annotations

from pathlib import Path

import pytest

from skillchef import store


def _make_fetched_skill(
    tmp_path: Path, *, body: str = "Base body", name: str = "hello-chef"
) -> Path:
    fetched = tmp_path / f"fetched-{name}"
    fetched.mkdir(parents=True, exist_ok=True)
    (fetched / "SKILL.md").write_text(f"---\nname: {name}\n---\n\n# Hello\n\n{body}\n")
    (fetched / "scripts").mkdir(exist_ok=True)
    (fetched / "scripts" / "tool.py").write_text("print('ok')\n")
    return fetched


def test_cook_layout_and_remove_cleanup(isolated_paths: dict[str, Path], tmp_path: Path) -> None:
    fetched = _make_fetched_skill(tmp_path)
    skill_dir = store.cook("hello-chef", fetched, "https://example.com/hello", "http", ["codex"])
    base = skill_dir / "base"
    live = skill_dir / "live"
    meta = store.load_meta("hello-chef")
    link = isolated_paths["platform_codex"] / "hello-chef"

    assert base.exists() and live.exists()
    assert (base / "SKILL.md").exists() and (live / "SKILL.md").exists()
    assert meta["name"] == "hello-chef"
    assert meta["remote_type"] == "http"
    assert meta["platforms"] == ["codex"]
    assert meta["enabled"] is True
    assert meta["base_sha256"] == store.hash_dir(base)
    assert meta["source_type"] == "http"
    assert meta["source_url"] == "https://example.com/hello"
    assert meta["source_path"] == "/hello"
    assert link.is_symlink()
    assert link.resolve() == live.resolve()

    store.remove("hello-chef")
    assert not skill_dir.exists()
    assert not link.exists()


def test_rebuild_live_and_update_base_refreshes_metadata(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    fetched = _make_fetched_skill(tmp_path, body="Original")
    store.cook("hello-chef", fetched, "https://example.com/hello", "http", ["codex"])

    flavor = store.flavor_path("hello-chef")
    flavor.write_text("Keep local behavior\n")
    old_base = store.base_skill_text("hello-chef")

    store.rebuild_live("hello-chef")
    live = store.live_skill_text("hello-chef")
    assert store.base_skill_text("hello-chef") == old_base
    assert "## Local Flavor" in live
    assert "Keep local behavior" in live
    assert live.index("Original") < live.index("## Local Flavor")

    new_fetched = _make_fetched_skill(tmp_path, body="v2", name="hello-chef")
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
    assert store.load_meta("hello-chef")["source_ref_resolved"] == "etag-2"


def test_hash_stability_and_scope_isolation(
    isolated_paths: dict[str, Path], tmp_path: Path, monkeypatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "b.txt").write_text("B")
    (first / "a.txt").write_text("A")
    (second / "a.txt").write_text("A")
    (second / "b.txt").write_text("B")
    assert store.hash_dir(first) == store.hash_dir(second)

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
    assert (
        store.load_meta("hello-chef", scope="global")["remote_url"] == "https://example.com/global"
    )
    assert (
        store.load_meta("hello-chef", scope="project")["remote_url"]
        == "https://example.com/project"
    )


def test_platform_path_guardrails(isolated_paths: dict[str, Path], tmp_path: Path) -> None:
    conflict = isolated_paths["platform_codex"] / "hello-chef"
    conflict.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Refusing to overwrite non-symlink"):
        store.cook("hello-chef", _make_fetched_skill(tmp_path), "local", "local", ["codex"])
    assert conflict.exists() and conflict.is_dir()

    store.cook(
        "other-chef", _make_fetched_skill(tmp_path, name="other-chef"), "local", "local", ["codex"]
    )
    link = isolated_paths["platform_codex"] / "other-chef"
    link.unlink()
    link.mkdir()
    with pytest.raises(RuntimeError, match="Refusing to remove non-symlink"):
        store.remove("other-chef")


def test_set_enabled_toggles_symlink(isolated_paths: dict[str, Path], tmp_path: Path) -> None:
    store.cook("hello-chef", _make_fetched_skill(tmp_path), "local", "local", ["codex"])
    link = isolated_paths["platform_codex"] / "hello-chef"
    live = store.skill_dir("hello-chef") / "live"

    assert link.is_symlink()
    assert link.resolve() == live.resolve()
    assert store.load_meta("hello-chef")["enabled"] is True

    store.set_enabled("hello-chef", enabled=False)
    assert not link.exists()
    assert store.load_meta("hello-chef")["enabled"] is False

    store.set_enabled("hello-chef", enabled=True)
    assert link.is_symlink()
    assert link.resolve() == live.resolve()
    assert store.load_meta("hello-chef")["enabled"] is True


def test_load_meta_defaults_enabled_for_legacy_meta(isolated_paths: dict[str, Path]) -> None:
    legacy_dir = store.skill_dir("legacy")
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "meta.toml").write_text(
        'name = "legacy"\nremote_url = "https://example.com"\nplatforms = ["codex"]\n'
    )

    meta = store.load_meta("legacy")
    assert meta["enabled"] is True


def test_flavor_path_legacy_fallback_and_named_flavors(
    isolated_paths: dict[str, Path], tmp_path: Path
) -> None:
    store.cook("hello-chef", _make_fetched_skill(tmp_path), "local", "local", ["codex"])
    legacy = store.skill_dir("hello-chef") / "flavor.md"
    legacy.write_text("legacy default\n")

    assert store.active_flavor_name("hello-chef") == "default"
    assert store.flavor_path("hello-chef") == legacy
    assert store.flavor_exists("hello-chef", "default")

    store.set_active_flavor("hello-chef", "project-a")
    project_path = store.named_flavor_path("hello-chef", "project-a")
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text("project flavor\n")

    assert store.active_flavor_name("hello-chef") == "project-a"
    assert store.flavor_path("hello-chef") == project_path
    assert store.flavor_exists("hello-chef", "project-a")
    assert store.list_flavor_names("hello-chef") == ["default", "project-a"]


def test_load_meta_defaults_active_flavor_for_legacy_meta(isolated_paths: dict[str, Path]) -> None:
    legacy_dir = store.skill_dir("legacy-two")
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "meta.toml").write_text(
        'name = "legacy-two"\nremote_url = "https://example.com"\nplatforms = ["codex"]\n'
    )

    meta = store.load_meta("legacy-two")
    assert meta["active_flavor"] == "default"
