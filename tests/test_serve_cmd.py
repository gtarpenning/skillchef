from __future__ import annotations

from pathlib import Path

import pytest

from skillchef import remote, store
from skillchef.commands import serve_cmd


def _write_live_skill(
    skill_name: str,
    isolated_paths: dict[str, Path],
    body: str = "Base body\n",
) -> Path:
    live_dir = isolated_paths["store_dir"] / skill_name / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / "SKILL.md").write_text(body)
    meta_dir = isolated_paths["store_dir"] / skill_name
    (meta_dir / "meta.toml").write_text(f'name = "{skill_name}"\nplatforms = ["codex"]\n')
    return live_dir


def _authenticated_credentials() -> remote.PublishCredentials:
    return remote.PublishCredentials(
        gh_installed=True,
        gh_authenticated=True,
        git_installed=True,
        git_configured=True,
    )


def test_serve_single_file_skill_defaults_to_gist(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_live_skill("demo", isolated_paths)
    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "choose", lambda _p, choices: choices[0])
    monkeypatch.setattr(serve_cmd.ui, "ask", lambda _p, default="": default)
    monkeypatch.setattr(serve_cmd.ui, "confirm", lambda _p, default=False: False)
    infos: list[str] = []
    successes: list[str] = []
    gist_calls: list[tuple[list[Path], str, bool]] = []
    monkeypatch.setattr(serve_cmd.ui, "info", lambda msg: infos.append(msg))
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "success", lambda msg: successes.append(msg))
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(
        serve_cmd.remote,
        "create_gist",
        lambda files, *, description, public: (
            gist_calls.append((files, description, public))
            or "https://gist.github.com/example/demo"
        ),
    )

    serve_cmd.run("demo")

    live_dir = store.skill_dir("demo") / "live"
    meta = store.load_meta("demo")
    cfg = serve_cmd.config.load(scope="global")
    assert gist_calls == [([live_dir / "SKILL.md"], "demo skill", False)]
    assert meta["served_url"] == "https://gist.github.com/example/demo"
    assert meta["served_kind"] == "gist"
    assert cfg["default_serve_target"] == ""
    assert any("GitHub CLI credentials detected." in msg for msg in infos)
    assert any("Remote URL:" in msg for msg in infos)
    assert successes


def test_serve_folder_skill_uses_repo_publish(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = _write_live_skill("folder-demo", isolated_paths)
    (live_dir / "scripts").mkdir()
    (live_dir / "scripts" / "run.sh").write_text("#!/bin/sh\necho hi\n")

    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(serve_cmd.ui, "info", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "confirm", lambda _p, default=False: False)
    monkeypatch.setattr(serve_cmd.ui, "choose", lambda _p, choices: choices[0])

    def ask(prompt: str, default: str = "") -> str:
        if prompt == "Existing repository (OWNER/REPO or URL)":
            return "acme/folder-demo"
        return default

    repo_calls: list[tuple[str, Path, str]] = []
    monkeypatch.setattr(serve_cmd.ui, "ask", ask)
    monkeypatch.setattr(
        serve_cmd.remote,
        "update_repo",
        lambda repo, source_dir, *, description: (
            repo_calls.append((repo, source_dir, description))
            or "https://github.com/acme/folder-demo"
        ),
    )

    serve_cmd.run("folder-demo")

    meta = store.load_meta("folder-demo")
    cfg = serve_cmd.config.load(scope="global")
    assert repo_calls == [("acme/folder-demo", live_dir, "folder-demo skill")]
    assert meta["served_url"] == "https://github.com/acme/folder-demo"
    assert meta["served_kind"] == "repo"
    assert meta["served_repo"] == "acme/folder-demo"
    assert cfg["default_serve_target"] == "https://github.com/acme/folder-demo"


def test_serve_existing_gist_shows_diff_and_updates_in_place(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = _write_live_skill("demo", isolated_paths, body="new body\n")
    store.record_served(
        "demo",
        url="https://gist.github.com/example/demo123",
        kind="gist",
        visibility="private",
    )
    (live_dir / "SKILL.md").write_text("updated body\n")

    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    infos: list[str] = []
    shown_diffs: list[list[str]] = []
    update_calls: list[tuple[str, list[Path], str]] = []
    monkeypatch.setattr(serve_cmd.ui, "info", lambda msg: infos.append(msg))
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "show_diff", lambda diff: shown_diffs.append(diff))
    monkeypatch.setattr(
        serve_cmd.ui,
        "confirm",
        lambda prompt, default=False: False if "re-cook" in prompt.lower() else True,
    )
    monkeypatch.setattr(serve_cmd.ui, "ask", lambda _p, default="": default)
    monkeypatch.setattr(
        serve_cmd.remote,
        "update_gist",
        lambda gist, files, *, description: (
            update_calls.append((gist, files, description))
            or "https://gist.github.com/example/demo123"
        ),
    )

    serve_cmd.run("demo")

    assert any("is served at" in msg for msg in infos)
    assert shown_diffs
    assert update_calls == [
        (
            "https://gist.github.com/example/demo123",
            [live_dir / "SKILL.md"],
            "demo skill",
        )
    ]


def test_serve_missing_gist_offers_new_publish_target(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = _write_live_skill("demo", isolated_paths, body="same body\n")
    store.record_served(
        "demo",
        url="https://gist.github.com/example/demo123",
        kind="gist",
        visibility="private",
    )
    warnings: list[str] = []
    created: list[tuple[list[Path], str, bool]] = []

    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(serve_cmd.ui, "info", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda msg: warnings.append(msg))
    monkeypatch.setattr(serve_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "show_diff", lambda _diff: None)
    monkeypatch.setattr(
        serve_cmd.ui,
        "confirm",
        lambda prompt, default=False: False if "re-cook" in prompt.lower() else True,
    )
    monkeypatch.setattr(serve_cmd.ui, "choose", lambda _p, choices: "github gist (secret)")
    monkeypatch.setattr(serve_cmd.ui, "ask", lambda _p, default="": default)
    monkeypatch.setattr(
        serve_cmd.remote,
        "update_gist",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            remote.PublishError("gh: Not Found (HTTP 404)")
        ),
    )
    monkeypatch.setattr(
        serve_cmd.remote,
        "create_gist",
        lambda files, *, description, public: (
            created.append((files, description, public))
            or "https://gist.github.com/example/newdemo"
        ),
    )

    serve_cmd.run("demo")

    assert any("could not be found" in msg for msg in warnings)
    assert created == [([live_dir / "SKILL.md"], "demo skill", False)]
    assert store.load_meta("demo")["served_url"] == "https://gist.github.com/example/newdemo"


def test_serve_uses_configured_default_target_for_first_publish(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_live_skill("demo", isolated_paths)
    serve_cmd.config.save(
        {
            "platforms": ["codex"],
            "editor": "vim",
            "model": "openai/gpt-5.2",
            "llm_api_key_env": "",
            "default_scope": "global",
            "default_serve_target": "https://github.com/acme/default-skill",
        }
    )
    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(serve_cmd.ui, "info", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "confirm", lambda _p, default=False: False)
    monkeypatch.setattr(serve_cmd.ui, "choose", lambda _p, choices: choices[0])
    monkeypatch.setattr(serve_cmd.ui, "ask", lambda _p, default="": default)
    repo_calls: list[tuple[str, Path, str]] = []
    monkeypatch.setattr(
        serve_cmd.remote,
        "update_repo",
        lambda repo, source_dir, *, description: (
            repo_calls.append((repo, source_dir, description))
            or "https://github.com/acme/default-skill"
        ),
    )

    serve_cmd.run("demo")

    assert repo_calls == [
        ("https://github.com/acme/default-skill", store.skill_dir("demo") / "live", "demo skill")
    ]


def test_serve_does_not_set_global_default_for_gist_publish(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_live_skill("demo", isolated_paths)
    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(serve_cmd.ui, "info", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "choose", lambda _p, choices: choices[0])
    monkeypatch.setattr(serve_cmd.ui, "ask", lambda _p, default="": default)
    monkeypatch.setattr(serve_cmd.ui, "confirm", lambda _p, default=False: False)
    monkeypatch.setattr(
        serve_cmd.remote,
        "create_gist",
        lambda *_args, **_kwargs: "https://gist.github.com/example/demo",
    )

    serve_cmd.run("demo")

    saved_cfg = serve_cmd.config.load(scope="global")
    assert saved_cfg["default_serve_target"] == ""


def test_serve_can_recook_from_newly_served_skill(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_live_skill("demo", isolated_paths)
    fetched = tmp_path / "served"
    fetched.mkdir()
    (fetched / "SKILL.md").write_text("served body\n")

    monkeypatch.setattr(serve_cmd.remote, "detect_publish_credentials", _authenticated_credentials)
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(serve_cmd.ui, "info", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "success", lambda _msg: None)
    monkeypatch.setattr(serve_cmd.ui, "choose", lambda _p, choices: choices[0])
    monkeypatch.setattr(
        serve_cmd.ui,
        "confirm",
        lambda prompt, default=False: "re-cook" in prompt.lower(),
    )
    monkeypatch.setattr(serve_cmd.ui, "ask", lambda _p, default="": default)
    monkeypatch.setattr(
        serve_cmd.remote,
        "create_gist",
        lambda *_args, **_kwargs: "https://gist.github.com/example/demo",
    )
    monkeypatch.setattr(
        serve_cmd.remote,
        "fetch",
        lambda _url: (fetched, "github"),
    )
    cleaned: list[Path] = []
    monkeypatch.setattr(serve_cmd, "cleanup_fetched", lambda path: cleaned.append(path))

    serve_cmd.run("demo")

    meta = store.load_meta("demo")
    assert meta["remote_url"] == "https://gist.github.com/example/demo"
    assert meta["served_url"] == "https://gist.github.com/example/demo"
    assert store.live_skill_text("demo") == "served body\n"
    assert cleaned == [fetched]


def test_serve_requires_gh_authentication_when_only_git_is_detected(
    isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_live_skill("demo", isolated_paths)
    warnings: list[str] = []
    monkeypatch.setattr(
        serve_cmd.remote,
        "detect_publish_credentials",
        lambda: remote.PublishCredentials(
            gh_installed=False,
            gh_authenticated=False,
            git_installed=True,
            git_configured=True,
        ),
    )
    monkeypatch.setattr(serve_cmd.ui, "banner", lambda: None)
    monkeypatch.setattr(serve_cmd.ui, "warn", lambda msg: warnings.append(msg))
    monkeypatch.setattr(serve_cmd.ui, "info", lambda _msg: None)

    with pytest.raises(SystemExit):
        serve_cmd.run("demo")

    assert any("Git credentials/config detected" in msg for msg in warnings)
