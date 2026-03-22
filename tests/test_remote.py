from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import httpx
import pytest

from skillchef import remote


def test_classify_recognizes_remote_sources() -> None:
    assert remote.classify("https://example.com/SKILL.md") == "http"
    assert (
        remote.classify("https://github.com/acme/repo/blob/main/skills/demo/SKILL.md") == "github"
    )
    assert remote.classify("https://github.com/acme/repo/tree/main/skills/demo") == "github"
    assert remote.classify("https://gist.github.com/acme/abcdef123456") == "github"


def test_classify_recognizes_local_source(tmp_path: Path) -> None:
    local = tmp_path / "SKILL.md"
    local.write_text("x")
    assert remote.classify(str(local)) == "local"


def test_classify_recognizes_home_relative_local_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    local = home / "demo-skill" / "SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("x")

    assert remote.classify("~/demo-skill/SKILL.md") == "local"


def test_classify_rejects_invalid_sources() -> None:
    invalid_sources = [
        ("https://example.com/skills/", "direct file URL"),
        ("https://github.com/acme/repo", "/blob|/tree"),
        ("definitely-not-a-path-or-url", "Cannot classify source"),
    ]
    for source, error_match in invalid_sources:
        with pytest.raises(ValueError, match=error_match):
            remote.classify(source)


def test_classify_missing_local_path_reports_specific_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing-skill"

    with pytest.raises(ValueError, match="Local source path does not exist"):
        remote.classify(str(missing))


def test_fetch_and_local_discovery_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "my-skill.md"
    src.write_text("content")
    calls: list[tuple[str, Path]] = []

    def fake_download(url: str, dest: Path) -> None:
        calls.append((url, dest))
        dest.write_text("---\nname: http-skill\n---\n")

    monkeypatch.setattr(remote, "_download_raw", fake_download)

    fetched_local = remote._fetch_local(str(src))
    fetched_http = remote._fetch_http("https://example.com/path/SKILL.md")

    copied = fetched_local / "my-skill.md"
    assert fetched_local.name == "skill"
    assert copied.exists()
    assert copied.read_text() == "content"

    assert len(calls) == 1
    assert calls[0][0] == "https://example.com/path/SKILL.md"
    file_path = fetched_http / "SKILL.md"
    assert file_path.exists()
    assert "http-skill" in file_path.read_text()

    root = tmp_path / "skills"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "SKILL.md").write_text("a")
    (root / "b" / "SKILL.md").write_text("b")

    assert len(remote.local_skill_candidates(str(root))) == 2


def test_github_parsing_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    blob = remote._parse_github_source(
        "https://github.com/acme/repo/blob/main/skills/demo/SKILL.md"
    )
    tree = remote._parse_github_source("https://github.com/acme/repo/tree/main/skills/demo")
    assert blob == ("acme", "repo", "main", "skills/demo/SKILL.md")
    assert tree == ("acme", "repo", "main", "skills/demo")
    assert remote._parse_gist_source("https://gist.github.com/acme/abcdef123456") == "abcdef123456"

    monkeypatch.setattr(remote, "_resolve_github_commit", lambda _o, _r, _ref: "abc123")
    meta = remote.source_metadata("https://github.com/acme/repo/blob/main/skills/demo/SKILL.md")
    assert meta["source_type"] == "github"
    assert meta["source_repo"] == "acme/repo"
    assert meta["source_path"] == "skills/demo/SKILL.md"
    assert meta["source_ref_requested"] == "main"
    assert meta["source_ref_resolved"] == "abc123"
    assert meta["source_commit_sha"] == "abc123"

    gist_meta = remote.source_metadata("https://gist.github.com/acme/abcdef123456")
    assert gist_meta["source_type"] == "github"
    assert gist_meta["source_repo"] == "gist"
    assert gist_meta["source_path"] == "abcdef123456"
    assert gist_meta["source_ref_requested"] == "abcdef123456"
    assert gist_meta["source_ref_resolved"] == "abcdef123456"


def test_source_metadata_for_http_and_local(tmp_path: Path) -> None:
    local = tmp_path / "SKILL.md"
    local.write_text("x")

    http_meta = remote.source_metadata("https://example.com/skills/SKILL.md")
    local_meta = remote.source_metadata(str(local))

    assert http_meta["source_type"] == "http"
    assert http_meta["source_path"] == "/skills/SKILL.md"
    assert local_meta["source_type"] == "local"
    assert local_meta["source_path"] == str(local.resolve())


def test_fetch_gist_downloads_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path]] = []

    def fake_request_json(url: str, *, headers=None) -> object:
        assert url == "https://api.github.com/gists/abcdef123456"
        return {
            "files": {
                "SKILL.md": {
                    "filename": "SKILL.md",
                    "content": "---\nname: gist-demo\n---\n",
                    "truncated": False,
                },
                "notes.txt": {
                    "filename": "notes.txt",
                    "content": "hello\n",
                    "truncated": False,
                },
            }
        }

    monkeypatch.setattr(remote, "_request_json_with_retry", fake_request_json)
    monkeypatch.setattr(
        remote,
        "_download_raw",
        lambda url, dest: calls.append((url, dest)),
    )

    fetched = remote._fetch_github("https://gist.github.com/acme/abcdef123456")

    assert (fetched / "SKILL.md").read_text() == "---\nname: gist-demo\n---\n"
    assert (fetched / "notes.txt").read_text() == "hello\n"
    assert calls == []


def test_request_with_retry_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    class DummyResponse:
        content = b"ok"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {"ok": True}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> DummyClient:
            return self

        def __exit__(self, *_args) -> bool:
            return False

        def get(self, _url: str, headers: dict[str, str] | None = None) -> DummyResponse:
            calls["count"] += 1
            if calls["count"] < 3:
                raise httpx.ReadTimeout("timeout")
            return DummyResponse()

    monkeypatch.setattr(remote.httpx, "Client", DummyClient)
    monkeypatch.setattr(remote.time, "sleep", lambda _n: None)

    data = remote._request_bytes_with_retry("https://example.com/SKILL.md")

    assert data == b"ok"
    assert calls["count"] == 3


def test_resolve_github_commit_logs_warning_on_lookup_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        remote,
        "_request_json_with_retry",
        lambda _url, headers=None: (_ for _ in ()).throw(remote.FetchError("network failed")),
    )

    caplog.set_level(logging.WARNING)
    sha = remote._resolve_github_commit("acme", "repo", "main")

    assert sha == ""
    assert "Could not resolve GitHub commit" in caplog.text


def test_detect_publish_credentials_parses_gh_and_git_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        remote.shutil,
        "which",
        lambda cmd: f"/usr/bin/{cmd}" if cmd in {"gh", "git"} else None,
    )

    def fake_run(cmd: list[str], **_kwargs):
        joined = " ".join(cmd)
        if cmd[:4] == ["gh", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout='{"hosts":{"github.com":{"activeAccount":{"state":"ok"}}}}',
                stderr="",
            )
        if joined == "git config --global --get credential.helper":
            return subprocess.CompletedProcess(cmd, 0, stdout="osxkeychain\n", stderr="")
        if joined == "git config --global --get user.name":
            return subprocess.CompletedProcess(cmd, 0, stdout="Chef\n", stderr="")
        if joined == "git config --global --get user.email":
            return subprocess.CompletedProcess(cmd, 0, stdout="chef@example.com\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)

    creds = remote.detect_publish_credentials()

    assert creds.gh_installed is True
    assert creds.gh_authenticated is True
    assert creds.git_installed is True
    assert creds.git_configured is True


def test_detect_publish_credentials_parses_current_gh_host_list_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        remote.shutil,
        "which",
        lambda cmd: f"/usr/bin/{cmd}" if cmd in {"gh", "git"} else None,
    )

    def fake_run(cmd: list[str], **_kwargs):
        joined = " ".join(cmd)
        if cmd[:4] == ["gh", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=(
                    '{"hosts":{"github.com":[{"state":"success","active":true,'
                    '"host":"github.com","login":"gtarpenning","tokenSource":"keyring"}]}}'
                ),
                stderr="",
            )
        if joined == "git config --global --get credential.helper":
            return subprocess.CompletedProcess(cmd, 0, stdout="osxkeychain\n", stderr="")
        if joined == "git config --global --get user.name":
            return subprocess.CompletedProcess(cmd, 0, stdout="Chef\n", stderr="")
        if joined == "git config --global --get user.email":
            return subprocess.CompletedProcess(cmd, 0, stdout="chef@example.com\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)

    creds = remote.detect_publish_credentials()

    assert creds.gh_authenticated is True


def test_create_gist_builds_expected_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("hi")
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout="https://gist.github.com/example/demo\n", stderr=""
        )

    monkeypatch.setattr(remote.subprocess, "run", fake_run)

    url = remote.create_gist([skill_md], description="demo skill", public=False)

    assert url == "https://gist.github.com/example/demo"
    assert calls == [["gh", "gist", "create", str(skill_md), "--desc", "demo skill"]]


def test_create_repo_builds_expected_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "live"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("hi")
    (source_dir / "script.sh").write_text("echo hi\n")
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd=None, **_kwargs):
        calls.append((cmd, cwd))
        stdout = "https://github.com/acme/demo\n" if cmd[:3] == ["gh", "repo", "create"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)

    url = remote.create_repo(
        source_dir,
        repo_name="acme/demo",
        description="demo skill",
        public=True,
    )

    assert url == "https://github.com/acme/demo"
    assert calls[0][0] == ["git", "init"]
    assert calls[1][0] == ["git", "add", "."]
    assert calls[2][0][:4] == ["git", "-c", "user.name=skillchef", "-c"]
    assert calls[3][0] == [
        "gh",
        "repo",
        "create",
        "acme/demo",
        "--source",
        ".",
        "--remote",
        "origin",
        "--push",
        "--description",
        "demo skill",
        "--public",
    ]


def test_update_gist_builds_expected_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("updated")
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)

    url = remote.update_gist(
        "https://gist.github.com/example/demo123",
        [skill_md],
        description="demo skill",
    )

    assert url == "https://gist.github.com/demo123"
    assert calls[0][:5] == ["gh", "api", "/gists/demo123", "--method", "PATCH"]


def test_update_repo_builds_expected_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "live"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("hi")
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd=None, **_kwargs):
        calls.append((cmd, cwd))
        if cmd[:3] == ["gh", "repo", "clone"]:
            Path(cmd[4]).mkdir(parents=True, exist_ok=True)
            (Path(cmd[4]) / ".git").mkdir()
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="M SKILL.md\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)

    url = remote.update_repo(
        "https://github.com/acme/demo",
        source_dir,
        description="demo skill",
    )

    assert url == "https://github.com/acme/demo"
    assert calls[0][0][:4] == ["gh", "repo", "clone", "acme/demo"]
    assert calls[1][0] == ["gh", "repo", "edit", "acme/demo", "--description", "demo skill"]
    assert calls[2][0] == ["git", "add", "-A"]
    assert calls[3][0] == ["git", "status", "--short"]
    assert calls[4][0][:4] == ["git", "-c", "user.name=skillchef", "-c"]
    assert calls[5][0] == ["git", "push", "origin", "HEAD"]
