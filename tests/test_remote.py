from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from skillchef import remote


def test_classify_distinguishes_local_http_and_github(tmp_path: Path) -> None:
    local = tmp_path / "SKILL.md"
    local.write_text("x")

    assert remote.classify(str(local)) == "local"
    assert remote.classify("https://example.com/SKILL.md") == "http"
    assert (
        remote.classify("https://github.com/acme/repo/blob/main/skills/demo/SKILL.md") == "github"
    )
    assert remote.classify("https://github.com/acme/repo/tree/main/skills/demo") == "github"


def test_classify_rejects_non_file_remote_urls() -> None:
    with pytest.raises(ValueError, match="direct file URL"):
        remote.classify("https://example.com/skills/")
    with pytest.raises(ValueError, match="/blob|/tree"):
        remote.classify("https://github.com/acme/repo")


def test_classify_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Cannot classify source"):
        remote.classify("definitely-not-a-path-or-url")


def test_fetch_local_file_preserves_filename(tmp_path: Path) -> None:
    src = tmp_path / "my-skill.md"
    src.write_text("content")

    fetched = remote._fetch_local(str(src))

    copied = fetched / "my-skill.md"
    assert fetched.name == "skill"
    assert copied.exists()
    assert copied.read_text() == "content"


def test_fetch_http_uses_download_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path]] = []

    def fake_download(url: str, dest: Path) -> None:
        calls.append((url, dest))
        dest.write_text("---\nname: http-skill\n---\n")

    monkeypatch.setattr(remote, "_download_raw", fake_download)

    fetched = remote._fetch_http("https://example.com/path/SKILL.md")
    file_path = fetched / "SKILL.md"

    assert len(calls) == 1
    assert calls[0][0] == "https://example.com/path/SKILL.md"
    assert file_path.exists()
    assert "http-skill" in file_path.read_text()


def test_local_skill_candidates_finds_nested_skill_files(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "SKILL.md").write_text("a")
    (root / "b" / "SKILL.md").write_text("b")

    candidates = remote.local_skill_candidates(str(root))

    assert len(candidates) == 2
    assert all(p.name == "SKILL.md" for p in candidates)


def test_parse_github_source_supports_blob_and_tree() -> None:
    blob = remote._parse_github_source(
        "https://github.com/acme/repo/blob/main/skills/demo/SKILL.md"
    )
    tree = remote._parse_github_source("https://github.com/acme/repo/tree/main/skills/demo")

    assert blob == ("acme", "repo", "main", "skills/demo/SKILL.md")
    assert tree == ("acme", "repo", "main", "skills/demo")


def test_source_metadata_for_github_uses_resolved_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(remote, "_resolve_github_commit", lambda _o, _r, _ref: "abc123")

    meta = remote.source_metadata("https://github.com/acme/repo/blob/main/skills/demo/SKILL.md")

    assert meta["source_type"] == "github"
    assert meta["source_repo"] == "acme/repo"
    assert meta["source_path"] == "skills/demo/SKILL.md"
    assert meta["source_ref_requested"] == "main"
    assert meta["source_ref_resolved"] == "abc123"
    assert meta["source_commit_sha"] == "abc123"


def test_source_metadata_for_http_and_local(tmp_path: Path) -> None:
    local = tmp_path / "SKILL.md"
    local.write_text("x")

    http_meta = remote.source_metadata("https://example.com/skills/SKILL.md")
    local_meta = remote.source_metadata(str(local))

    assert http_meta["source_type"] == "http"
    assert http_meta["source_path"] == "/skills/SKILL.md"
    assert local_meta["source_type"] == "local"
    assert local_meta["source_path"] == str(local.resolve())


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
