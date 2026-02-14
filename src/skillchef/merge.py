from __future__ import annotations

import difflib
import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
FLAVOR_HEADER = "\n\n## Local Flavor\n\n"


def split_frontmatter(text: str) -> tuple[str, str]:
    m = FRONTMATTER_RE.match(text)
    if m:
        return text[: m.end()], text[m.end() :]
    return "", text


def merge_skill(live_skill_path: Path, flavor_path: Path) -> None:
    base_text = live_skill_path.read_text()
    flavor_text = flavor_path.read_text().strip()
    if not flavor_text:
        return
    front, body = split_frontmatter(base_text)
    body = body.rstrip()
    merged = front + body + FLAVOR_HEADER + flavor_text + "\n"
    live_skill_path.write_text(merged)


def diff_texts(old: str, new: str, label_old: str = "old", label_new: str = "new") -> list[str]:
    return list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=label_old,
        tofile=label_new,
    ))


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
