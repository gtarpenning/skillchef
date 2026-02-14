from __future__ import annotations

import difflib
import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
FLAVOR_HEADER = "\n\n## Local Flavor\n\n"
FLAVOR_SECTION_RE = re.compile(r"(?m)^##\s+Local Flavor\s*$")


def split_frontmatter(text: str) -> tuple[str, str]:
    m = FRONTMATTER_RE.match(text)
    if m:
        return text[: m.end()], text[m.end() :]
    return "", text


def merge_skill(live_skill_path: Path, flavor_path: Path) -> None:
    merged = merge_skill_text(live_skill_path.read_text(), flavor_path.read_text())
    live_skill_path.write_text(merged)


def merge_skill_text(base_text: str, flavor_text: str) -> str:
    flavor = flavor_text.strip()
    if not flavor:
        return _ensure_newline(base_text)
    front, body = split_frontmatter(base_text)
    body = body.rstrip()
    return front + body + FLAVOR_HEADER + flavor + "\n"


def split_local_flavor_section(text: str) -> tuple[str, str | None]:
    match = FLAVOR_SECTION_RE.search(text)
    if not match:
        return text, None
    base = text[: match.start()]
    flavor = text[match.end() :]
    return _ensure_newline(base.rstrip()), flavor.strip("\n")


def has_non_flavor_local_changes(old_base: str, current_live: str) -> bool:
    live_without_flavor, _ = split_local_flavor_section(current_live)
    return _normalize_for_compare(live_without_flavor) != _normalize_for_compare(old_base)


def diff_texts(old: str, new: str, label_old: str = "old", label_new: str = "new") -> list[str]:
    return list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=label_old,
            tofile=label_new,
        )
    )


def three_way_summary(old_base: str, new_remote: str, flavor: str) -> str:
    lines = []
    base_diff = diff_texts(old_base, new_remote, "base (old)", "remote (new)")
    if base_diff:
        lines.append("=== Upstream changes ===")
        lines.extend(base_diff)
    if flavor.strip():
        lines.append("\n=== Your flavor ===")
        lines.append(flavor)
    return "".join(lines)


def _normalize_for_compare(text: str) -> str:
    return _ensure_newline(text).rstrip("\n")


def _ensure_newline(text: str) -> str:
    if not text:
        return ""
    return text if text.endswith("\n") else text + "\n"
