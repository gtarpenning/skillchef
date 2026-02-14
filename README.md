# skillchef

Cook, flavor & sync agent skills from any source.

## Chef it up

```
uvx skillchef
```

## Flavoring your first skill

```bash
uvx skillchef init
uvx skillchef cook https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
uvx skillchef flavor

# next week
uvx skillchef sync
```

## How does the chef work his magic?

Skills are stored in `~/.skillchef/store/<name>/` with three layers:

```
base/       ← pristine copy from remote
flavor.md   ← your local additions (optional)
live/       ← merged result (base + flavor), symlinked into platform dirs
```

`cook` fetches a skill and symlinks it into your configured platform directories (`~/.codex/skills/`, `~/.cursor/skills/`, etc).

`sync` checks the remote for changes. If your skill has a flavor, it shows the upstream diff and proposes a semantic merge via LLM (auto-detected from env API keys).

`flavor` opens your editor to add local customizations that persist across syncs.

## What can I cook?

- **GitHub**: `https://github.com/user/repo/tree/main/path/to/skill`
- **HTTP**: any direct URL to a SKILL.md file
- **Local**: path to a skill directory or file on disk

## What does the kitchen look like?

Here is what your local setup currently looks like on disk:

```text
~/.skillchef/store/
  frontend-design/
    base/
      SKILL.md        # upstream source snapshot
    flavor.md         # your local customizations
    live/
      SKILL.md        # merged output (base + flavor)
    meta.toml         # source + sync metadata
```

And those `live/` directories are what get linked into each platform:

```text
~/.codex/skills/
  frontend-design -> ~/.skillchef/store/frontend-design/live
~/.cursor/skills/
  frontend-design -> ~/.skillchef/store/frontend-design/live
...
```

When you run `sync`, SkillChef fetches the latest upstream `SKILL.md` and updates `base/SKILL.md`.
Then it re-renders `live/SKILL.md` by applying your `flavor.md` on top, and updates `meta.toml` (hash + last sync timestamp).
The symlink paths in `~/<>/skills/` keep pointing at the same `live/` directory.
