from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

GITHUB_TREE_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)/(?P<path>.+)"
)
GITHUB_BLOB_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
)


def classify(source: str) -> str:
    if Path(source).exists():
        return "local"
    parsed = urlparse(source)
    if "github.com" in (parsed.hostname or ""):
        return "github"
    if parsed.scheme in ("http", "https"):
        return "http"
    raise ValueError(f"Cannot classify source: {source}")


def fetch(source: str) -> tuple[Path, str]:
    """Fetch skill content into a temp directory.
    Returns (temp_dir_path, remote_type).
    Caller is responsible for cleanup.
    """
    kind = classify(source)
    if kind == "local":
        return _fetch_local(source), kind
    if kind == "github":
        return _fetch_github(source), kind
    return _fetch_http(source), kind


def _fetch_local(source: str) -> Path:
    src = Path(source).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    if src.is_dir():
        shutil.copytree(src, tmp / "skill", dirs_exist_ok=True)
        return tmp / "skill"
    tmp_skill = tmp / "skill"
    tmp_skill.mkdir()
    shutil.copy2(src, tmp_skill / src.name)
    return tmp_skill


def _fetch_github(source: str) -> Path:
    m = GITHUB_TREE_RE.search(source) or GITHUB_BLOB_RE.search(source)
    if not m:
        raise ValueError(f"Cannot parse GitHub URL: {source}")
    owner, repo, ref, path = m.group("owner"), m.group("repo"), m.group("ref"), m.group("path")
    return _fetch_github_dir(owner, repo, ref, path)


def _fetch_github_dir(owner: str, repo: str, ref: str, path: str) -> Path:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    skill_dir = tmp / "skill"
    skill_dir.mkdir()
    _download_github_path(api_url, skill_dir)
    return skill_dir


def _download_github_path(api_url: str, dest: Path) -> None:
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        resp = client.get(api_url, headers={"Accept": "application/vnd.github.v3+json"})
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and data.get("type") == "file":
        _download_raw(data["download_url"], dest / data["name"])
        return

    if isinstance(data, list):
        for item in data:
            if item["type"] == "file":
                _download_raw(item["download_url"], dest / item["name"])
            elif item["type"] == "dir":
                sub = dest / item["name"]
                sub.mkdir(exist_ok=True)
                _download_github_path(item["url"], sub)


def _download_raw(url: str, dest: Path) -> None:
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def _fetch_http(source: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    skill_dir = tmp / "skill"
    skill_dir.mkdir()
    parsed = urlparse(source)
    filename = Path(parsed.path).name or "SKILL.md"
    _download_raw(source, skill_dir / filename)
    return skill_dir
