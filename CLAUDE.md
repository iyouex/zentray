# CLAUDE.md

本文件为 Claude Code 会话提供本项目的工作约定。

## 项目概述

**ZenTray** —— 跨平台（Windows / macOS / Linux）系统托盘 GTD + 番茄钟 + AI 计划/复盘。
Python 后端 + Vue 前端（`web/`）。详见 [README.md](README.md)。

## Git 工作流（2026-08-25 起）

采用 **feature → staging → master** 三层流程。**`main` 分支已废弃删除，勿再使用。**

| 分支 | 职责 |
|------|------|
| `master` | 稳定发布线，GitHub 默认分支，仅在发版时由 staging 合入并打 tag |
| `staging` | 集成测试线，feature 合入后在此验证 |
| `feature/*` | 功能开发分支，一律从 **staging** 切出 |
| `hotfix/*` | 紧急修复分支，从 **master** 切出 |

### 操作规则

- 新功能：`git switch -c feature/<name> staging`
- 功能完成：合入 staging，在 staging 上测试验证；**不要直接向 master 提交**
- 发版：staging → master，随后按 [docs/VERSIONING.md](docs/VERSIONING.md) 同步三处版本号（`zentray/config.py` / `pyproject.toml` / `installer/install_wizard.py`）并打 tag：`git tag vX.Y.Z && git push origin vX.Y.Z`
- 热修复：从 master 切出 `hotfix/<name>`，修完**同时合回 master 和 staging**。这是唯一不经 staging 直达 master 的例外；若构成一次发布，同样需同步版本号并打 tag
- **发版操作（staging → master 合并、打 tag、推送）须经用户明确确认后执行**
- 提交信息沿用现有风格：`feat:` / `fix:` 等前缀 + 中文描述
- 提交信息沿用现有风格：`feat:` / `fix:` 等前缀 + 中文描述

### 存量搁置分支

以下分支为迁移前的存量工作，**未经用户指示不要改动**；恢复开发时先 rebase 到最新 staging，再按上述流程合入：

- `feature/win-tray-title`
- `feature/plugin-scripts-services`
- `backup/plugin-scripts-with-morning`

### 历史备注

- 迁移前旧 master 的历史存档于 tag `archive/master-before-migration`
- 迁移前主分支为 `main`，2026-08-25 由 master 接管
