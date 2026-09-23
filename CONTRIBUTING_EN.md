# Contributing to ZenTray

[简体中文](CONTRIBUTING.md) | English | [日本語](CONTRIBUTING_JA.md)

Thanks for your interest in ZenTray! This project uses a three-tier branching model: **feature → staging → master**.

## Branch Model

| Branch | Role | How it's updated |
|--------|------|------------------|
| `master` | Stable release line (GitHub default branch) | Merged from staging only at release time, tagged `vX.Y.Z` |
| `staging` | Integration / testing line | Feature branches merge here for verification |
| `feature/*` | Feature development branches | Cut from **staging** |
| `hotfix/*` | Urgent fix branches | Cut from **master** |

> Historical note: the project previously used `main` as its trunk; it was retired on 2026-08-25. Do not use it.

## Day-to-Day Workflow

1. Cut a feature branch from staging:

   ```bash
   git switch -c feature/your-feature staging
   ```

2. Develop and commit. Commit message format: `feat: add something` / `fix: correct something`

3. When done, open a Pull Request against **staging** (or have a maintainer merge it), then verify on staging.

4. At release time, merge staging into **master** and tag. Versioning follows semver; before releasing, sync the three version locations per [docs/VERSIONING.md](docs/VERSIONING.md) (`zentray/config.py` / `pyproject.toml` / `installer/install_wizard.py`).

## Hotfixes

```bash
git switch -c hotfix/urgent-fix master
# After fixing, merge back into BOTH master and staging — neither can be skipped
```

Hotfixes are the only exception allowed to reach `master` without passing through staging; if one constitutes a release, sync the version number and tag per [docs/VERSIONING.md](docs/VERSIONING.md) as well.

## Ground Rules

- Never push directly to `master`
- Do not use the retired `main` branch
