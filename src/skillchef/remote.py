from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
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
GITHUB_GIST_RE = re.compile(r"gist\.github\.com/(?:[^/]+/)?(?P<gist_id>[A-Za-z0-9]+)")


class RemoteError(RuntimeError):
    """Base class for remote fetch errors."""


class FetchError(RemoteError):
    """Raised when remote content cannot be fetched."""


class MetadataResolutionError(RemoteError):
    """Raised when source metadata cannot be resolved."""


class PublishError(RemoteError):
    """Raised when remote publishing fails."""


@dataclass(frozen=True)
class PublishCredentials:
    gh_installed: bool
    gh_authenticated: bool
    git_installed: bool
    git_configured: bool


def classify(source: str) -> str:
    local_path = Path(source).expanduser()
    if local_path.exists():
        return "local"

    parsed = urlparse(source)
    if "gist.github.com" in (parsed.hostname or ""):
        if not _parse_gist_source(source):
            raise ValueError(
                "GitHub gist source must be a gist URL like https://gist.github.com/<id>"
            )
        return "github"
    if "github.com" in (parsed.hostname or ""):
        if not _parse_github_source(source):
            raise ValueError("GitHub source must use /blob/.../SKILL.md or /tree/.../<skill-dir>")
        return "github"
    if parsed.scheme in ("http", "https"):
        if parsed.path.endswith("/") or not Path(parsed.path).name:
            raise ValueError("HTTP source must be a direct file URL")
        return "http"

    if _looks_like_local_path(source):
        raise ValueError(f"Local source path does not exist: {local_path}")

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
        if parsed:
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

        gist_id = _parse_gist_source(source)
        if gist_id:
            metadata.update(
                {
                    "source_repo": "gist",
                    "source_path": gist_id,
                    "source_ref_requested": gist_id,
                    "source_ref_resolved": gist_id,
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
    if parsed:
        owner, repo, ref, path = parsed
        return _fetch_github_dir(owner, repo, ref, path)

    gist_id = _parse_gist_source(source)
    if gist_id:
        return _fetch_gist(gist_id)

    if not parsed:
        raise ValueError(
            "Cannot parse GitHub URL. Use /blob/.../SKILL.md, /tree/.../<skill-dir>, or a gist URL."
        )
    raise AssertionError("unreachable")


def _fetch_github_dir(owner: str, repo: str, ref: str, path: str) -> Path:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    skill_dir = tmp / "skill"
    skill_dir.mkdir()
    _download_github_path(api_url, skill_dir)
    return skill_dir


def _download_github_path(api_url: str, dest: Path) -> None:
    data = _request_json_with_retry(api_url, headers={"Accept": "application/vnd.github.v3+json"})

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


def _fetch_gist(gist_id: str) -> Path:
    api_url = f"https://api.github.com/gists/{gist_id}"
    data = _request_json_with_retry(api_url, headers={"Accept": "application/vnd.github.v3+json"})
    if not isinstance(data, dict):
        raise FetchError(f"Unexpected GitHub gist response format for {api_url}")

    payload = cast(dict[str, Any], data)
    files = payload.get("files")
    if not isinstance(files, dict):
        raise FetchError(f"GitHub gist response missing files for {api_url}")

    tmp = Path(tempfile.mkdtemp(prefix="skillchef-"))
    skill_dir = tmp / "skill"
    skill_dir.mkdir()

    for raw_name, raw_file in files.items():
        if not isinstance(raw_file, dict):
            continue
        file_payload = cast(dict[str, Any], raw_file)
        filename = str(file_payload.get("filename") or raw_name).strip()
        if not filename:
            continue
        dest = skill_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        content = file_payload.get("content")
        truncated = bool(file_payload.get("truncated"))
        if isinstance(content, str) and not truncated:
            dest.write_text(content)
            continue

        raw_url = str(file_payload.get("raw_url", "")).strip()
        if not raw_url:
            raise FetchError(f"GitHub gist file missing retrievable content for {api_url}")
        _download_raw(raw_url, dest)

    return skill_dir


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


def _parse_gist_source(source: str) -> str | None:
    match = GITHUB_GIST_RE.search(source)
    if not match:
        return None
    return match.group("gist_id")


def _resolve_github_commit(owner: str, repo: str, ref: str) -> str:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
    try:
        data = _request_json_with_retry(
            api_url, headers={"Accept": "application/vnd.github.v3+json"}
        )
        if not isinstance(data, dict):
            raise MetadataResolutionError(
                f"Unexpected response type for commit lookup: {type(data)}"
            )
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


def detect_publish_credentials() -> PublishCredentials:
    gh_installed = shutil.which("gh") is not None
    git_installed = shutil.which("git") is not None

    gh_authenticated = False
    if gh_installed:
        try:
            result = subprocess.run(
                ["gh", "auth", "status", "--json", "hosts"],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout or "{}")
            hosts = payload.get("hosts", {})
            gh_authenticated = any(_gh_host_authenticated(host) for host in _iter_gh_hosts(hosts))
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            gh_authenticated = False

    git_configured = False
    if git_installed:
        helper = _git_config_value("credential.helper")
        user_name = _git_config_value("user.name")
        user_email = _git_config_value("user.email")
        git_configured = bool(helper or (user_name and user_email))

    return PublishCredentials(
        gh_installed=gh_installed,
        gh_authenticated=gh_authenticated,
        git_installed=git_installed,
        git_configured=git_configured,
    )


def create_gist(files: list[Path], *, description: str, public: bool) -> str:
    if not files:
        raise PublishError("No files were provided for gist publishing.")

    cmd = ["gh", "gist", "create", *[str(path) for path in files], "--desc", description]
    if public:
        cmd.append("--public")
    return _run_publish_command(cmd)


def update_gist(gist: str, files: list[Path], *, description: str) -> str:
    if len(files) != 1:
        raise PublishError("Updating a gist currently supports exactly one file.")

    file_path = files[0]
    gist_id = _gist_id_from_value(gist)
    payload = {
        "description": description,
        "files": {
            file_path.name: {
                "content": file_path.read_text(),
            }
        },
    }
    tmp_root = Path(tempfile.mkdtemp(prefix="skillchef-gist-"))
    payload_path = tmp_root / "payload.json"
    try:
        payload_path.write_text(json.dumps(payload))
        _run_publish_command(
            ["gh", "api", f"/gists/{gist_id}", "--method", "PATCH", "--input", str(payload_path)]
        )
        return f"https://gist.github.com/{gist_id}"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def create_repo(source_dir: Path, *, repo_name: str, description: str, public: bool) -> str:
    if not source_dir.exists():
        raise PublishError(f"Skill directory does not exist: {source_dir}")

    tmp_root = Path(tempfile.mkdtemp(prefix="skillchef-publish-"))
    repo_dir = tmp_root / "repo"
    repo_dir.mkdir()
    try:
        for entry in source_dir.iterdir():
            dest = repo_dir / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dest)
            else:
                shutil.copy2(entry, dest)

        _run_publish_command(["git", "init"], cwd=repo_dir)
        _run_publish_command(["git", "add", "."], cwd=repo_dir)
        _run_publish_command(
            [
                "git",
                "-c",
                "user.name=skillchef",
                "-c",
                "user.email=skillchef@local",
                "commit",
                "-m",
                "Initial skill export",
            ],
            cwd=repo_dir,
        )

        cmd = [
            "gh",
            "repo",
            "create",
            repo_name,
            "--source",
            ".",
            "--remote",
            "origin",
            "--push",
            "--description",
            description,
        ]
        cmd.append("--public" if public else "--private")
        return _run_publish_command(cmd, cwd=repo_dir)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def update_repo(repo: str, source_dir: Path, *, description: str) -> str:
    if not source_dir.exists():
        raise PublishError(f"Skill directory does not exist: {source_dir}")

    repo_name = _repo_name_from_value(repo)
    tmp_root = Path(tempfile.mkdtemp(prefix="skillchef-publish-"))
    clone_dir = tmp_root / "repo"
    try:
        _run_publish_command(["gh", "repo", "clone", repo_name, str(clone_dir)])
        _clear_repo_worktree(clone_dir)
        for entry in source_dir.iterdir():
            dest = clone_dir / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dest)
            else:
                shutil.copy2(entry, dest)

        _run_publish_command(["gh", "repo", "edit", repo_name, "--description", description])
        _run_publish_command(["git", "add", "-A"], cwd=clone_dir)
        status = _run_capture_command(["git", "status", "--short"], cwd=clone_dir).strip()
        if not status:
            return f"https://github.com/{repo_name}"

        _run_publish_command(
            [
                "git",
                "-c",
                "user.name=skillchef",
                "-c",
                "user.email=skillchef@local",
                "commit",
                "-m",
                "Update served skill",
            ],
            cwd=clone_dir,
        )
        _run_publish_command(["git", "push", "origin", "HEAD"], cwd=clone_dir)
        return f"https://github.com/{repo_name}"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def _run_publish_command(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise PublishError(f"Command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise PublishError(message or f"Command failed: {' '.join(cmd)}") from exc

    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return ""
    return output.splitlines()[-1].strip()


def _run_capture_command(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise PublishError(f"Command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise PublishError(message or f"Command failed: {' '.join(cmd)}") from exc
    return result.stdout or ""


def _iter_gh_hosts(raw_hosts: object) -> list[dict[str, Any]]:
    if isinstance(raw_hosts, list):
        return [cast(dict[str, Any], item) for item in raw_hosts if isinstance(item, dict)]
    if isinstance(raw_hosts, dict):
        values: list[dict[str, Any]] = []
        for hostname, value in raw_hosts.items():
            if isinstance(value, dict):
                item = cast(dict[str, Any], value).copy()
                item.setdefault("hostname", hostname)
                values.append(item)
                continue
            if isinstance(value, list):
                for raw_item in value:
                    if not isinstance(raw_item, dict):
                        continue
                    item = cast(dict[str, Any], raw_item).copy()
                    item.setdefault("hostname", hostname)
                    values.append(item)
        return values
    return []


def _gh_host_authenticated(host: dict[str, Any]) -> bool:
    token = str(host.get("token", "")).strip()
    if token:
        return True

    state = str(host.get("state", "")).strip().lower()
    if state in {"ok", "logged in", "success"}:
        return True

    if bool(host.get("active")):
        token_source = str(host.get("tokenSource", "")).strip()
        if token_source:
            return True

    active = host.get("activeAccount")
    if isinstance(active, dict):
        state = str(active.get("state", "")).strip().lower()
        if state in {"ok", "logged in", "success"}:
            return True
        token_source = str(active.get("tokenSource", "")).strip()
        if token_source:
            return True

    status = str(host.get("status", "")).strip().lower()
    if status in {"ok", "logged in", "success"}:
        return True

    return False


def _git_config_value(key: str) -> str:
    try:
        result = subprocess.run(
            ["git", "config", "--global", "--get", key],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _looks_like_local_path(source: str) -> bool:
    return source.startswith(("/", "./", "../", "~")) or "/" in source or "\\" in source


def _gist_id_from_value(gist: str) -> str:
    path = urlparse(gist).path.strip("/")
    if path:
        return path.split("/")[-1]
    return gist.strip()


def _repo_name_from_value(repo: str) -> str:
    path = urlparse(repo).path.strip("/")
    if path:
        return path
    return repo.strip()


def _clear_repo_worktree(repo_dir: Path) -> None:
    for entry in repo_dir.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
