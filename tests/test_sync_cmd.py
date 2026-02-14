from __future__ import annotations

from concurrent.futures import Future, TimeoutError
from pathlib import Path

import pytest

from skillchef.commands import sync_cmd


def _write_skill(path: Path, text: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(text)


def test_resolve_ai_future_returns_value() -> None:
    fut: Future[str] = Future()
    fut.set_result("merged")

    assert sync_cmd._resolve_ai_future(fut) == "merged"


def test_resolve_ai_future_handles_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[str] = []

    class DummySpinner:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    fut: Future[str] = Future()
    fut.set_exception(RuntimeError("boom"))

    monkeypatch.setattr(sync_cmd.ui, "spinner", lambda _msg: DummySpinner())
    monkeypatch.setattr(sync_cmd.ui, "warn", lambda msg: warnings.append(msg))

    assert sync_cmd._resolve_ai_future(fut) is None
    assert warnings and "AI merge failed" in warnings[0]


def test_resolve_ai_future_can_skip_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    infos: list[str] = []

    class DummySpinner:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    class SlowFuture:
        def result(self, timeout=None):
            raise TimeoutError

    polls = {"count": 0}

    def fake_poll_delete_key() -> bool:
        polls["count"] += 1
        return polls["count"] > 1

    monkeypatch.setattr(sync_cmd.ui, "spinner", lambda _msg: DummySpinner())
    monkeypatch.setattr(sync_cmd.ui, "poll_delete_key", fake_poll_delete_key)
    monkeypatch.setattr(sync_cmd.ui, "info", lambda msg: infos.append(msg))

    assert sync_cmd._resolve_ai_future(SlowFuture()) is None  # type: ignore[arg-type]
    assert any("Skipping initial AI proposal" in msg for msg in infos)


def test_sync_one_updates_base_and_live_when_no_flavor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fetched = tmp_path / "remote"
    _write_skill(fetched, "---\nname: hello-chef\n---\n\nremote new\n")

    calls: dict[str, int] = {"update": 0, "rebuild": 0, "cleanup": 0}

    monkeypatch.setattr(sync_cmd.remote, "fetch", lambda _url: (fetched, "http"))
    monkeypatch.setattr(sync_cmd.store, "hash_dir", lambda _p: "newhash")
    monkeypatch.setattr(sync_cmd.store, "base_skill_text", lambda _n: "old base\n")
    monkeypatch.setattr(sync_cmd.store, "has_flavor", lambda _n: False)
    monkeypatch.setattr(
        sync_cmd.store,
        "update_base",
        lambda _n, _d: calls.__setitem__("update", calls["update"] + 1),
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "rebuild_live",
        lambda _n: calls.__setitem__("rebuild", calls["rebuild"] + 1),
    )
    monkeypatch.setattr(sync_cmd.ui, "confirm", lambda _p: True)
    monkeypatch.setattr(sync_cmd.ui, "show_diff", lambda _d: None)
    monkeypatch.setattr(sync_cmd.ui, "info", lambda _m: None)
    monkeypatch.setattr(sync_cmd.ui, "success", lambda _m: None)
    monkeypatch.setattr(
        sync_cmd, "cleanup_fetched", lambda _p: calls.__setitem__("cleanup", calls["cleanup"] + 1)
    )

    meta = {"name": "hello-chef", "remote_url": "https://example.com", "base_sha256": "oldhash"}
    sync_cmd._sync_one(meta, ai_available=False)

    assert calls["update"] == 1
    assert calls["rebuild"] == 1
    assert calls["cleanup"] == 1


def test_sync_one_accepts_ai_merge_and_writes_live_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_paths: dict[str, Path],
) -> None:
    skill_name = "hello-chef"
    live_dir = isolated_paths["store_dir"] / skill_name / "live"
    base_dir = isolated_paths["store_dir"] / skill_name / "base"
    _write_skill(live_dir, "old live\n")
    _write_skill(base_dir, "old base\n")
    flavor_path = isolated_paths["store_dir"] / skill_name / "flavor.md"
    flavor_path.parent.mkdir(parents=True, exist_ok=True)
    flavor_path.write_text("local flavor\n")

    fetched = tmp_path / "remote"
    _write_skill(fetched, "new remote\n")

    calls: dict[str, int] = {"update": 0, "cleanup": 0}

    monkeypatch.setattr(sync_cmd.remote, "fetch", lambda _url: (fetched, "http"))
    monkeypatch.setattr(sync_cmd.store, "hash_dir", lambda _p: "newhash")
    monkeypatch.setattr(sync_cmd.store, "base_skill_text", lambda _n: "old base\n")
    monkeypatch.setattr(sync_cmd.store, "has_flavor", lambda _n: True)
    monkeypatch.setattr(sync_cmd.store, "flavor_path", lambda _n: flavor_path)
    monkeypatch.setattr(sync_cmd.store, "live_skill_text", lambda _n: "old live\n")
    monkeypatch.setattr(
        sync_cmd.store, "skill_dir", lambda _n: isolated_paths["store_dir"] / skill_name
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "update_base",
        lambda _n, _d: calls.__setitem__("update", calls["update"] + 1),
    )
    monkeypatch.setattr(sync_cmd.ui, "show_diff", lambda _d: None)
    monkeypatch.setattr(sync_cmd.ui, "info", lambda _m: None)
    monkeypatch.setattr(sync_cmd.ui, "success", lambda _m: None)
    monkeypatch.setattr(sync_cmd.ui, "choose", lambda _p, _c: "accept ai merge")
    monkeypatch.setattr(sync_cmd, "semantic_merge", lambda *_a, **_k: "merged output\n")
    monkeypatch.setattr(
        sync_cmd, "cleanup_fetched", lambda _p: calls.__setitem__("cleanup", calls["cleanup"] + 1)
    )

    meta = {"name": skill_name, "remote_url": "https://example.com", "base_sha256": "oldhash"}
    sync_cmd._sync_one(meta, ai_available=True)

    assert calls["update"] == 1
    assert calls["cleanup"] == 1
    assert (live_dir / "SKILL.md").read_text() == "merged output\n"


def test_sync_one_no_conflicts_preserves_live_local_flavor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_paths: dict[str, Path],
) -> None:
    skill_name = "hello-chef"
    live_dir = isolated_paths["store_dir"] / skill_name / "live"
    base_dir = isolated_paths["store_dir"] / skill_name / "base"
    old_base = "# Skill\n\nBase body\n"
    current_live = old_base + "\n## Local Flavor\n\nKeep current live flavor\n"
    _write_skill(live_dir, current_live)
    _write_skill(base_dir, old_base)

    flavor_path = isolated_paths["store_dir"] / skill_name / "flavor.md"
    flavor_path.parent.mkdir(parents=True, exist_ok=True)
    flavor_path.write_text("outdated flavor\n")

    fetched = tmp_path / "remote"
    _write_skill(fetched, "# Skill\n\nRemote updated base\n")

    calls: dict[str, int] = {"update": 0, "cleanup": 0}
    choices: list[list[str]] = []
    semantic_calls: dict[str, int] = {"count": 0}

    monkeypatch.setattr(sync_cmd.remote, "fetch", lambda _url: (fetched, "http"))
    monkeypatch.setattr(sync_cmd.store, "hash_dir", lambda _p: "newhash")
    monkeypatch.setattr(sync_cmd.store, "base_skill_text", lambda _n: old_base)
    monkeypatch.setattr(sync_cmd.store, "has_flavor", lambda _n: True)
    monkeypatch.setattr(sync_cmd.store, "flavor_path", lambda _n: flavor_path)
    monkeypatch.setattr(sync_cmd.store, "live_skill_text", lambda _n: (live_dir / "SKILL.md").read_text())
    monkeypatch.setattr(
        sync_cmd.store, "skill_dir", lambda _n: isolated_paths["store_dir"] / skill_name
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "update_base",
        lambda _n, _d: calls.__setitem__("update", calls["update"] + 1),
    )
    monkeypatch.setattr(sync_cmd.ui, "show_diff", lambda _d: None)
    monkeypatch.setattr(sync_cmd.ui, "info", lambda _m: None)
    monkeypatch.setattr(sync_cmd.ui, "success", lambda _m: None)
    monkeypatch.setattr(
        sync_cmd.ui,
        "choose",
        lambda _p, opts: (choices.append(list(opts)) or "accept update"),
    )
    def fake_semantic_merge(*_args, **_kwargs) -> str:
        semantic_calls["count"] += 1
        return "# Skill\n\nRemote updated base\n\n## Local Flavor\n\nKeep current live flavor\n"

    monkeypatch.setattr(sync_cmd, "semantic_merge", fake_semantic_merge)
    monkeypatch.setattr(
        sync_cmd, "cleanup_fetched", lambda _p: calls.__setitem__("cleanup", calls["cleanup"] + 1)
    )

    meta = {"name": skill_name, "remote_url": "https://example.com", "base_sha256": "oldhash"}
    sync_cmd._sync_one(meta, ai_available=True)

    assert calls["update"] == 1
    assert calls["cleanup"] == 1
    assert semantic_calls["count"] == 1
    assert choices and "accept ai merge" not in choices[0]
    assert "resolve with chat" not in choices[0]
    assert "Keep current live flavor" in (live_dir / "SKILL.md").read_text()
    assert flavor_path.read_text().strip() == "Keep current live flavor"
