from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from skillchef import cli


def test_cli_main_first_run_routes_to_init(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_first_run", lambda cwd=None: True)
    monkeypatch.setattr("skillchef.ui.banner", lambda: None)
    monkeypatch.setattr("skillchef.ui.info", lambda _msg: None)

    for choice, expected_run_wizard in [
        ("init + onboarding wizard (recommended)", True),
        ("init only", False),
    ]:
        called: dict[str, object] = {}
        monkeypatch.setattr("skillchef.ui.choose", lambda _p, _c, c=choice: c)
        monkeypatch.setattr(
            cli.init_cmd,
            "run",
            lambda scope="auto", run_wizard=None, payload=called: (
                payload.setdefault("scope", scope),
                payload.setdefault("run_wizard", run_wizard),
            ),
        )

        result = CliRunner().invoke(cli.main, [])

        assert result.exit_code == 0
        assert called["scope"] == "auto"
        assert called["run_wizard"] is expected_run_wizard


def test_cli_main_non_first_run_shows_help(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_is_first_run", lambda cwd=None: False)

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_cli_init_dispatches_wizard_option(monkeypatch) -> None:
    for args, expected_wizard in [
        (["init"], None),
        (["init", "--wizard"], True),
        (["init", "--no-wizard"], False),
    ]:
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            cli.init_cmd,
            "run",
            lambda scope="auto", run_wizard=None, payload=captured: (
                payload.setdefault("scope", scope),
                payload.setdefault("run_wizard", run_wizard),
            ),
        )

        result = CliRunner().invoke(cli.main, args)

        assert result.exit_code == 0
        assert captured["scope"] == "auto"
        assert captured["run_wizard"] is expected_wizard


def test_is_first_run_detects_global_or_project_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.config, "SKILLCHEF_HOME", tmp_path / "global-home")
    workdir = tmp_path / "project"
    workdir.mkdir()

    assert cli._is_first_run(workdir)

    (tmp_path / "global-home").mkdir(parents=True)
    assert not cli._is_first_run(workdir)

    monkeypatch.setattr(cli.config, "SKILLCHEF_HOME", tmp_path / "missing-home")
    (workdir / ".skillchef").mkdir(parents=True)
    assert not cli._is_first_run(workdir)


def test_cli_cook_dispatches_to_command(monkeypatch) -> None:
    for args, expected_force_overwrite in [
        (["cook", "https://example.com/skill"], False),
        (["cook", "--force-overwrite", "https://example.com/skill"], True),
    ]:
        captured: dict[str, object] = {}

        monkeypatch.setattr(
            cli.cook_cmd,
            "run",
            lambda source, force_overwrite=False, scope="auto", payload=captured: (
                payload.setdefault("source", source),
                payload.setdefault("force_overwrite", force_overwrite),
                payload.setdefault("scope", scope),
            ),
        )

        result = CliRunner().invoke(cli.main, args)

        assert result.exit_code == 0
        assert captured["source"] == "https://example.com/skill"
        assert captured["force_overwrite"] is expected_force_overwrite
        assert captured["scope"] == "auto"


def test_cli_inspect_dispatches_to_command(monkeypatch) -> None:
    for args, expected_skill_name in [
        (["inspect", "hello-chef"], "hello-chef"),
        (["inspect"], None),
    ]:
        captured: dict[str, str | None] = {}
        monkeypatch.setattr(
            cli.inspect_cmd,
            "run",
            lambda skill_name, scope="auto", payload=captured: (
                payload.setdefault("skill_name", skill_name),
                payload.setdefault("scope", scope),
            ),
        )

        result = CliRunner().invoke(cli.main, args)

        assert result.exit_code == 0
        assert captured["skill_name"] == expected_skill_name
        assert captured["scope"] == "auto"
