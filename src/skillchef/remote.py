from __future__ import annotations

import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_MAX_ATTEMPTS = 3
REQUEST_BACKOFF_SECONDS = 0.25

GITHUB_BLOB_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
)
GITHUB_TREE_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)/(?P<path>.+)"
)


class RemoteError(RuntimeError):
    """Base class for remote fetch errors."""


class FetchError(RemoteError):
    """Raised when remote content cannot be fetched."""


class MetadataResolutionError(RemoteError):
    """Raised when source metadata cannot be resolved."""


def classify(source: str) -> str:
    if Path(source).exists():
        return "local"
    parsed = urlparse(source)
    if "github.com" in (parsed.hostname or ""):
        if not _parse_github_source(source):
            raise ValueError(
                "GitHub source must use /blob/.../SKILL.md or /tree/.../<skill-dir>"
            )
        return "github"
    if parsed.scheme in ("http", "https"):
        if parsed.path.endswith("/") or not Path(parsed.path).name:
            raise ValueError("HTTP source must be a direct file URL")
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


def source_metadata(source: str, remote_type: str | None = None) -> dict[str, str]:
    kind = remote_type or classify(source)
    metadata = {
        "source_type": kind,
        "source_url": source,
        "source_repo": "",
        "source_path": "",
        "source_ref_requested": "",
        "source_ref_resolved": "",
        "source_commit_sha": "",
    }

    if kind == "github":
        parsed = _parse_github_source(source)
        if not parsed:
            return metadata
        owner, repo, ref, path = parsed
        commit_sha = _resolve_github_commit(owner, repo, ref)
        metadata.update(
            {
                "source_repo": f"{owner}/{repo}",
                "source_path": path,
                "source_ref_requested": ref,
                "source_ref_resolved": commit_sha or ref,
                "source_commit_sha": commit_sha,
            }
        )
        return metadata

    if kind == "http":
        metadata["source_path"] = urlparse(source).path
        return metadata

    metadata["source_path"] = str(Path(source).resolve())
    return metadata


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
    parsed = _parse_github_source(source)
    if not parsed:
        raise ValueError(
            "Cannot parse GitHub URL. Use /blob/.../SKILL.md or /tree/.../<skill-dir>."
        )
    owner, repo, ref, path = parsed
    return _fetch_github_dir(owner, repo, ref, path)


def _fetch_github_dir(owner: str, repo: str, ref: str, path: str) -> Path:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    skill_dir = tmp / "skill"
    skill_dir.mkdir()
    _download_github_path(api_url, skill_dir)
    return skill_dir


def _download_github_path(api_url: str, dest: Path) -> None:
    data = _request_json_with_retry(
        api_url, headers={"Accept": "application/vnd.github.v3+json"}
    )

    if isinstance(data, dict):
        item = cast(dict[str, Any], data)
        if item.get("type") == "file":
            download_url = str(item.get("download_url", "")).strip()
            name = str(item.get("name", "")).strip()
            if not download_url or not name:
                raise FetchError(f"GitHub API file response missing required fields for {api_url}")
            _download_raw(download_url, dest / name)
            return

    if isinstance(data, list):
        for raw_item in data:
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, Any], raw_item)
            item_type = item.get("type")
            if item_type == "file":
                _download_raw(str(item["download_url"]), dest / str(item["name"]))
            elif item_type == "dir":
                sub = dest / str(item["name"])
                sub.mkdir(exist_ok=True)
                _download_github_path(str(item["url"]), sub)
        return

    raise FetchError(f"Unexpected GitHub API response format for {api_url}")


def _download_raw(url: str, dest: Path) -> None:
    content = _request_bytes_with_retry(url)
    dest.write_bytes(content)


def _fetch_http(source: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    skill_dir = tmp / "skill"
    skill_dir.mkdir()
    parsed = urlparse(source)
    filename = Path(parsed.path).name or "SKILL.md"
    _download_raw(source, skill_dir / filename)
    return skill_dir


def local_skill_candidates(source: str) -> list[Path]:
    src = Path(source).resolve()
    if src.is_file():
        if src.name == "SKILL.md":
            return [src]
        return []
    if not src.is_dir():
        return []

    found: list[Path] = []
    if (src / "SKILL.md").exists():
        found.append(src / "SKILL.md")
    found.extend(sorted(p for p in src.rglob("SKILL.md") if p != src / "SKILL.md"))
    return found


def _parse_github_source(source: str) -> tuple[str, str, str, str] | None:
    for regex in (GITHUB_BLOB_RE, GITHUB_TREE_RE):
        match = regex.search(source)
        if match:
            return (
                match.group("owner"),
                match.group("repo"),
                match.group("ref"),
                match.group("path"),
            )
    return None


def _resolve_github_commit(owner: str, repo: str, ref: str) -> str:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
    try:
        data = _request_json_with_retry(
            api_url, headers={"Accept": "application/vnd.github.v3+json"}
        )
        if not isinstance(data, dict):
            raise MetadataResolutionError(f"Unexpected response type for commit lookup: {type(data)}")
        payload = cast(dict[str, Any], data)
        return str(payload.get("sha", "")).strip()
    except (FetchError, MetadataResolutionError) as exc:
        logger.warning(
            "Could not resolve GitHub commit for %s/%s@%s: %s",
            owner,
            repo,
            ref,
            exc,
        )
        return ""


def _request_json_with_retry(url: str, *, headers: dict[str, str] | None = None) -> object:
    response = _request_with_retry(url, headers=headers)
    try:
        return response.json()
    except ValueError as exc:
        raise FetchError(f"Invalid JSON response from {url}") from exc


def _request_bytes_with_retry(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    response = _request_with_retry(url, headers=headers)
    return response.content


def _request_with_retry(url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                return response
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == REQUEST_MAX_ATTEMPTS:
                break
            time.sleep(REQUEST_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    raise FetchError(f"Failed to fetch {url}: {last_error}") from last_error
