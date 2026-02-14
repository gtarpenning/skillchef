from __future__ import annotations

from pathlib import Path

import pytest

from skillchef import remote


def test_classify_distinguishes_local_http_and_github(tmp_path: Path) -> None:
    local = tmp_path / "SKILL.md"
    local.write_text("x")

    assert remote.classify(str(local)) == "local"
    assert remote.classify("https://example.com/SKILL.md") == "http"
    assert remote.classify("https://github.com/acme/repo/tree/main/skills/demo") == "github"


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
