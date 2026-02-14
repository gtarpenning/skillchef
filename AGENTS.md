# AGENTS.md

## Purpose
Guide agents to make safe, fast, repo-consistent changes in `skill-chef` (Python CLI for cooking/flavoring/syncing skills).

## Repo Snapshot
- Language: Python `>=3.11`
- Package manager/runtime: `uv`
- CLI entrypoint: `src/skillchef/cli.py` (`skillchef`)
- Core modules:
  - `src/skillchef/commands/*`: command flows (`init`, `cook`, `sync`, `flavor`, `list`, `inspect`, `remove`)
  - `src/skillchef/store.py`: store layout, metadata, symlinks
  - `src/skillchef/remote.py`: source classification/fetch + GitHub metadata resolution
  - `src/skillchef/merge.py`: deterministic SKILL merge behavior
  - `src/skillchef/llm.py`: semantic merge via LiteLLM + logging
  - `src/skillchef/ui.py`: all terminal UI/prompt primitives
- Tests: `tests/` (unit + e2e via `click.testing.CliRunner`)

## Critical Behavior To Preserve
- Store layout per skill:
  - `base/` upstream snapshot
  - `live/` effective skill content
  - `flavor.md` optional local overlay
  - `meta.toml` provenance/sync metadata
- `sync` semantics:
  - no upstream changes: no-op
  - no flavor: prompt accept/skip, update base/live
  - with flavor: preserve `## Local Flavor` intent and avoid contradictory merged instructions
- Platform links must point to `<skill>/live` (symlink behavior in `store._create_symlinks`).
- Scope behavior (`global` vs `project` vs `auto`) must remain consistent with `config.resolve_scope`.

## Local Dev Commands
- Run tests: `uv run pytest`
- Run a focused test: `uv run pytest tests/test_sync_cmd.py -q`
- Lint/format/type checks:
  - `uv run --extra dev ruff format`
  - `uv run --extra dev ruff check`
  - `uv run --extra dev ty check`
- Run CLI locally: `uv run skillchef --help`

## Change Workflow For Agents
1. Read the command/module you will touch plus related tests.
2. Keep UI-only changes in `ui.py`; keep command decisions in `commands/*`; keep persistence logic in `store.py`.
3. Add/adjust tests in `tests/` for behavior changes (prefer nearest existing test file).
4. Run targeted tests first, then broader suite.
5. If changing CLI flags/flows, update both tests and `README.md`.

## Testing Guidance (Repo-Specific)
- Prefer monkeypatching UI functions in tests to avoid interactive prompts.
- Use `isolated_paths` fixture for filesystem isolation and HOME/config/store patching.
- For sync/merge behavior, assert both:
  - final `live/SKILL.md` content
  - metadata/symlink side effects when relevant
- For command dispatch changes, update `tests/test_cli.py`.
- For full-flow regressions, add/extend `tests/test_e2e_cli.py`.

## Guardrails
- Do not mix unrelated refactors with behavior fixes; this repo relies on clear command boundaries.
- Do not bypass `store` APIs when changing persisted state.
- Preserve newline/frontmatter handling in `merge.py`.
- Keep non-interactive behavior working (fallback numeric/text choice flow in `ui.py`).
- Avoid introducing network calls in tests; mock `remote.fetch`/LLM calls.

## Known Operational Details
- LLM completion logs default to `.skillchef-logs/llm-completions.log` (override with `SKILLCHEF_LLM_LOG_DIR`).
- Config defaults live in `config.DEFAULT_CONFIG`; `init` writes user config.
- Pre-commit hook (`.githooks/pre-commit`) runs format + lint + `ty` checks; keep changes compatible.

## When Unsure
- Follow existing tests as source of truth for expected behavior.
- If behavior is ambiguous, prefer preserving current sync/flavor semantics over introducing new merge rules.
