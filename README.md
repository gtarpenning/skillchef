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
uvx skillchef inspect frontend-design

# next week
uvx skillchef sync
```

`init` offers an optional guided onboarding wizard after setup. It uses the `frontend-design` skill and walks through `cook -> flavor -> sync` so you can see flavor-preserving sync behavior end to end. If you already set up skillchef and want to run it directly, use `uvx skillchef init --wizard`.

## How does the chef work his magic?

Skills are stored in `~/.skillchef/store/<name>/` with three layers:

```
base/       ← pristine copy from remote
flavor.md   ← your local additions (optional)
live/       ← merged result (base + flavor), symlinked into platform dirs
```

`cook` fetches a skill and symlinks it into your configured platform directories (`~/.codex/skills/`, etc).

`list` shows whether each cooked skill is `[enabled|disabled]`; in interactive mode you can disable/enable a skill without removing it.

`sync` checks the remote for changes. If your skill has a flavor, it shows the upstream diff and proposes a semantic merge via LLM (auto-detected from env API keys).

`flavor` opens your editor to add local customizations that persist across syncs.
You can keep multiple named flavors per skill:

```bash
uvx skillchef flavor frontend-design --name project-a   # create/edit + set active
uvx skillchef flavor frontend-design --name project-b   # create/edit + set active
uvx skillchef flavor frontend-design --use project-a    # switch active flavor
```

`serve` publishes a managed skill from its `live/` content. Single-file skills default to a GitHub gist when `gh` credentials are detected. Multi-file skills prompt for a destination, with an existing GitHub repository offered as the primary option. Each served skill records its own remote as that skill's serve target. A configured global default applies only to repository targets and is used for unserved skills. When a skill has a served remote recorded, `serve` shows the diff between the current `live/` content and the served snapshot, updates the existing remote in place, and can optionally re-cook the skill from the served URL.

## What can I cook?

- **GitHub file**: `https://github.com/user/repo/blob/main/path/to/skill/SKILL.md`
- **GitHub directory**: `https://github.com/user/repo/tree/main/path/to/skill`
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
Then it re-renders `live/SKILL.md` by applying your `flavor.md` on top, and updates `meta.toml` (hash, last sync timestamp, and source provenance fields such as repo/path/ref/commit when available).
The symlink paths in `~/<>/skills/` keep pointing at the same `live/` directory.
