from __future__ import annotations

from pathlib import Path

from skillchef import merge


def test_split_frontmatter_handles_present_and_absent() -> None:
    frontmatter_text = "---\nname: demo\n---\n# Body\n"
    front, body = merge.split_frontmatter(frontmatter_text)

    assert front.startswith("---\nname: demo")
    assert body == "# Body\n"

    no_front, plain_body = merge.split_frontmatter("# No Frontmatter\n")
    assert no_front == ""
    assert plain_body == "# No Frontmatter\n"


def test_merge_skill_preserves_frontmatter_and_normalizes_output(tmp_path: Path) -> None:
    live = tmp_path / "SKILL.md"
    flavor = tmp_path / "flavor.md"

    live.write_text("---\nname: hello\n---\n\n# Heading\n\nBase body\n\n")
    flavor.write_text("\nLocal override line\n")

    merge.merge_skill(live, flavor)
    merged = live.read_text()

    assert merged.startswith("---\nname: hello\n---\n")
    assert merge.FLAVOR_HEADER in merged
    assert "Base body" in merged and "Local override line" in merged
    assert merged.endswith("\n")


def test_three_way_summary_includes_upstream_and_flavor_sections() -> None:
    summary = merge.three_way_summary(
        old_base="# Title\nOld line\n",
        new_remote="# Title\nNew line\n",
        flavor="Keep this local\n",
    )

    assert "=== Upstream changes ===" in summary
    assert "=== Your flavor ===" in summary
    assert "-Old line" in summary and "+New line" in summary
    assert "Keep this local" in summary


def test_split_local_flavor_section_extracts_trailing_local_section() -> None:
    text = "# Skill\n\nBase\n\n## Local Flavor\n\nKeep this\n"
    base, flavor = merge.split_local_flavor_section(text)

    assert base == "# Skill\n\nBase\n"
    assert flavor == "Keep this"


def test_has_non_flavor_local_changes_ignores_flavor_section_only() -> None:
    old_base = "# Skill\n\nBase\n"
    current_live = "# Skill\n\nBase\n\n## Local Flavor\n\nKeep this\n"

    assert not merge.has_non_flavor_local_changes(old_base, current_live)
