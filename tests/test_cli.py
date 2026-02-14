from __future__ import annotations

from click.testing import CliRunner

from skillchef import cli


def test_cli_cook_dispatches_to_command(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli.cook_cmd,
        "run",
        lambda source, force_overwrite=False, scope="auto": (
            captured.setdefault("source", source),
            captured.setdefault("force_overwrite", force_overwrite),
            captured.setdefault("scope", scope),
        ),
    )

    result = CliRunner().invoke(cli.main, ["cook", "https://example.com/skill"])

    assert result.exit_code == 0
    assert captured["source"] == "https://example.com/skill"
    assert captured["force_overwrite"] is False
    assert captured["scope"] == "auto"


def test_cli_cook_dispatches_force_overwrite(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli.cook_cmd,
        "run",
        lambda source, force_overwrite=False, scope="auto": (
            captured.setdefault("source", source),
            captured.setdefault("force_overwrite", force_overwrite),
            captured.setdefault("scope", scope),
        ),
    )

    result = CliRunner().invoke(cli.main, ["cook", "--force-overwrite", "https://example.com/skill"])

    assert result.exit_code == 0
    assert captured["source"] == "https://example.com/skill"
    assert captured["force_overwrite"] is True
    assert captured["scope"] == "auto"


def test_cli_inspect_dispatches_to_command(monkeypatch) -> None:
    captured: dict[str, str | None] = {}
    monkeypatch.setattr(
        cli.inspect_cmd,
        "run",
        lambda skill_name, scope="auto": (
            captured.setdefault("skill_name", skill_name),
            captured.setdefault("scope", scope),
        ),
    )

    result = CliRunner().invoke(cli.main, ["inspect", "hello-chef"])

    assert result.exit_code == 0
    assert captured["skill_name"] == "hello-chef"
    assert captured["scope"] == "auto"


def test_cli_inspect_without_name_dispatches_to_command(monkeypatch) -> None:
    captured: dict[str, str | None] = {}
    monkeypatch.setattr(
        cli.inspect_cmd,
        "run",
        lambda skill_name, scope="auto": (
            captured.setdefault("skill_name", skill_name),
            captured.setdefault("scope", scope),
        ),
    )

    result = CliRunner().invoke(cli.main, ["inspect"])

    assert result.exit_code == 0
    assert captured["skill_name"] is None
    assert captured["scope"] == "auto"
