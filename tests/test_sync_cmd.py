from __future__ import annotations

from concurrent.futures import Future, TimeoutError
from pathlib import Path

import pytest

from skillchef.commands import sync_cmd


def _write_skill(path: Path, text: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(text)


def test_resolve_ai_future_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[str] = []
    infos: list[str] = []

    class DummySpinner:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(sync_cmd.ui, "spinner", lambda _msg: DummySpinner())
    monkeypatch.setattr(sync_cmd.ui, "warn", lambda msg: warnings.append(msg))
    monkeypatch.setattr(sync_cmd.ui, "info", lambda msg: infos.append(msg))

    success_future: Future[str] = Future()
    success_future.set_result("merged")
    assert sync_cmd._resolve_ai_future(success_future) == "merged"

    fut: Future[str] = Future()
    fut.set_exception(RuntimeError("boom"))
    assert sync_cmd._resolve_ai_future(fut) is None
    assert warnings and "AI merge failed" in warnings[0]

    class SlowFuture:
        def result(self, timeout=None):
            raise TimeoutError

    polls = {"count": 0}

    def fake_poll_delete_key() -> bool:
        polls["count"] += 1
        return polls["count"] > 1

    monkeypatch.setattr(sync_cmd.ui, "poll_delete_key", fake_poll_delete_key)

    assert sync_cmd._resolve_ai_future(SlowFuture()) is None  # type: ignore[arg-type]
    assert any("Skipping initial AI proposal" in msg for msg in infos)


def test_sync_one_core_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_paths: dict[str, Path],
) -> None:
    monkeypatch.setattr(sync_cmd.store, "hash_dir", lambda _p: "newhash")
    monkeypatch.setattr(sync_cmd.ui, "show_diff", lambda _d: None)
    monkeypatch.setattr(sync_cmd.ui, "info", lambda _m: None)
    monkeypatch.setattr(sync_cmd.ui, "success", lambda _m: None)

    # no flavor path
    no_flavor_fetched = tmp_path / "remote-no-flavor"
    _write_skill(no_flavor_fetched, "---\nname: plain-chef\n---\n\nremote new\n")
    no_flavor_calls: dict[str, int] = {"update": 0, "rebuild": 0, "cleanup": 0}
    monkeypatch.setattr(sync_cmd.remote, "fetch", lambda _url: (no_flavor_fetched, "http"))
    monkeypatch.setattr(sync_cmd.store, "base_skill_text", lambda _n, scope="auto": "old base\n")
    monkeypatch.setattr(sync_cmd.store, "has_flavor", lambda _n, scope="auto": False)
    monkeypatch.setattr(
        sync_cmd.store,
        "update_base",
        lambda _n, _d, scope="auto": no_flavor_calls.__setitem__(
            "update", no_flavor_calls["update"] + 1
        ),
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "rebuild_live",
        lambda _n, scope="auto": no_flavor_calls.__setitem__(
            "rebuild", no_flavor_calls["rebuild"] + 1
        ),
    )
    monkeypatch.setattr(sync_cmd.ui, "confirm", lambda _p: True)
    monkeypatch.setattr(
        sync_cmd,
        "cleanup_fetched",
        lambda _p: no_flavor_calls.__setitem__("cleanup", no_flavor_calls["cleanup"] + 1),
    )
    sync_cmd._sync_one(
        {"name": "plain-chef", "remote_url": "https://example.com/plain", "base_sha256": "oldhash"},
        ai_available=False,
    )
    assert no_flavor_calls == {"update": 1, "rebuild": 1, "cleanup": 1}

    # flavor conflict path accepts AI merge
    ai_skill = "ai-chef"
    ai_live_dir = isolated_paths["store_dir"] / ai_skill / "live"
    ai_base_dir = isolated_paths["store_dir"] / ai_skill / "base"
    _write_skill(ai_live_dir, "old live\n")
    _write_skill(ai_base_dir, "old base\n")
    ai_flavor_path = isolated_paths["store_dir"] / ai_skill / "flavor.md"
    ai_flavor_path.parent.mkdir(parents=True, exist_ok=True)
    ai_flavor_path.write_text("local flavor\n")
    ai_fetched = tmp_path / "remote-ai"
    _write_skill(ai_fetched, "new remote\n")
    ai_calls: dict[str, int] = {"update": 0, "cleanup": 0}
    monkeypatch.setattr(sync_cmd.remote, "fetch", lambda _url: (ai_fetched, "http"))
    monkeypatch.setattr(sync_cmd.store, "base_skill_text", lambda _n, scope="auto": "old base\n")
    monkeypatch.setattr(sync_cmd.store, "has_flavor", lambda _n, scope="auto": True)
    monkeypatch.setattr(sync_cmd.store, "flavor_path", lambda _n, scope="auto": ai_flavor_path)
    monkeypatch.setattr(sync_cmd.store, "live_skill_text", lambda _n, scope="auto": "old live\n")
    monkeypatch.setattr(
        sync_cmd.store,
        "skill_dir",
        lambda _n, scope="auto": isolated_paths["store_dir"] / ai_skill,
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "update_base",
        lambda _n, _d, scope="auto": ai_calls.__setitem__("update", ai_calls["update"] + 1),
    )
    monkeypatch.setattr(sync_cmd.ui, "choose", lambda _p, _c: "accept ai merge")
    monkeypatch.setattr(sync_cmd, "semantic_merge", lambda *_a, **_k: "merged output\n")
    monkeypatch.setattr(
        sync_cmd,
        "cleanup_fetched",
        lambda _p: ai_calls.__setitem__("cleanup", ai_calls["cleanup"] + 1),
    )
    sync_cmd._sync_one(
        {"name": ai_skill, "remote_url": "https://example.com/ai", "base_sha256": "oldhash"},
        ai_available=True,
    )
    assert ai_calls == {"update": 1, "cleanup": 1}
    assert (ai_live_dir / "SKILL.md").read_text() == "merged output\n"

    # no-conflict path keeps current local flavor and omits AI options
    keep_skill = "keep-chef"
    keep_live_dir = isolated_paths["store_dir"] / keep_skill / "live"
    keep_base_dir = isolated_paths["store_dir"] / keep_skill / "base"
    old_base = "# Skill\n\nBase body\n"
    current_live = old_base + "\n## Local Flavor\n\nKeep current live flavor\n"
    _write_skill(keep_live_dir, current_live)
    _write_skill(keep_base_dir, old_base)
    keep_flavor_path = isolated_paths["store_dir"] / keep_skill / "flavor.md"
    keep_flavor_path.parent.mkdir(parents=True, exist_ok=True)
    keep_flavor_path.write_text("outdated flavor\n")
    keep_fetched = tmp_path / "remote-keep"
    _write_skill(keep_fetched, "# Skill\n\nRemote updated base\n")
    keep_calls: dict[str, int] = {"update": 0, "cleanup": 0}
    choices: list[list[str]] = []
    semantic_calls: dict[str, int] = {"count": 0}
    monkeypatch.setattr(sync_cmd.remote, "fetch", lambda _url: (keep_fetched, "http"))
    monkeypatch.setattr(sync_cmd.store, "base_skill_text", lambda _n, scope="auto": old_base)
    monkeypatch.setattr(sync_cmd.store, "has_flavor", lambda _n, scope="auto": True)
    monkeypatch.setattr(sync_cmd.store, "flavor_path", lambda _n, scope="auto": keep_flavor_path)
    monkeypatch.setattr(
        sync_cmd.store,
        "live_skill_text",
        lambda _n, scope="auto": (keep_live_dir / "SKILL.md").read_text(),
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "skill_dir",
        lambda _n, scope="auto": isolated_paths["store_dir"] / keep_skill,
    )
    monkeypatch.setattr(
        sync_cmd.store,
        "update_base",
        lambda _n, _d, scope="auto": keep_calls.__setitem__("update", keep_calls["update"] + 1),
    )
    monkeypatch.setattr(
        sync_cmd.ui,
        "choose",
        lambda _p, opts: choices.append(list(opts)) or "accept update",
    )

    def fake_semantic_merge(*_args, **_kwargs) -> str:
        semantic_calls["count"] += 1
        return "# Skill\n\nRemote updated base\n\n## Local Flavor\n\nKeep current live flavor\n"

    monkeypatch.setattr(sync_cmd, "semantic_merge", fake_semantic_merge)
    monkeypatch.setattr(
        sync_cmd,
        "cleanup_fetched",
        lambda _p: keep_calls.__setitem__("cleanup", keep_calls["cleanup"] + 1),
    )
    sync_cmd._sync_one(
        {"name": keep_skill, "remote_url": "https://example.com/keep", "base_sha256": "oldhash"},
        ai_available=True,
    )
    assert keep_calls == {"update": 1, "cleanup": 1}
    assert semantic_calls["count"] == 1
    assert choices and "accept ai merge" not in choices[0]
    assert "resolve with chat" not in choices[0]
    assert "Keep current live flavor" in (keep_live_dir / "SKILL.md").read_text()
    assert keep_flavor_path.read_text().strip() == "outdated flavor"
