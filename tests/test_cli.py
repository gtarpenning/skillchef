from __future__ import annotations

from click.testing import CliRunner

from skillchef import cli


def test_cli_cook_dispatches_to_command(monkeypatch) -> None:
    captured: dict[str, str] = {}

    monkeypatch.setattr(cli.cook_cmd, "run", lambda source: captured.setdefault("source", source))

    result = CliRunner().invoke(cli.main, ["cook", "https://example.com/skill"])

    assert result.exit_code == 0
    assert captured["source"] == "https://example.com/skill"
