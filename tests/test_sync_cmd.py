from __future__ import annotations

from concurrent.futures import Future
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
