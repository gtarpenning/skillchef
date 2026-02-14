# skillchef

Cook, flavor & sync agent skills from any source.

## Install

```
uvx skillchef
```

## Quickstart

```bash
uvx skillchef init
uvx skillchef cook https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
uvx skillchef flavor

# next week
uvx skillchef sync
```

## Usage

```
skillchef init                    # configure platforms, editor, AI model
skillchef cook <source>           # import a skill (GitHub URL, HTTP URL, local path)
skillchef sync [skill-name]       # pull upstream changes, merge with your flavor
skillchef flavor [skill-name]     # edit local customizations in $EDITOR
skillchef list                    # show all managed skills
skillchef remove <skill-name>     # remove a skill and its symlinks
```

## How it works

Skills are stored in `~/.skillchef/store/<name>/` with three layers:

```
base/       ← pristine copy from remote
flavor.md   ← your local additions (optional)
live/       ← merged result (base + flavor), symlinked into platform dirs
```

`cook` fetches a skill and symlinks it into your configured platform directories (`~/.codex/skills/`, `~/.cursor/skills/`, etc).

`sync` checks the remote for changes. If your skill has a flavor, it shows the upstream diff and proposes a semantic merge via LLM (auto-detected from env API keys).

`flavor` opens your editor to add local customizations that persist across syncs.

## Remote sources

- **GitHub**: `https://github.com/user/repo/tree/main/path/to/skill`
- **HTTP**: any direct URL to a SKILL.md file
- **Local**: path to a skill directory or file on disk

## Testing

```
uv sync --extra test
pytest -q
```

Run pre-commit hooks manually: `./.githooks/pre-commit`.

The suite lives in `tests/` and focuses on:
- storage lifecycle (`cook`, `rebuild_live`, `remove`)
- remote source classification/fetch behavior
- merge semantics and flavor application
- key sync command branches (no-flavor update and AI-merge path)
