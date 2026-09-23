# 贡献指南

[简体中文](CONTRIBUTING.md) | [English](CONTRIBUTING_EN.md) | [日本語](CONTRIBUTING_JA.md)

感谢关注 ZenTray！本项目采用 **feature → staging → master** 三层分支模型。

## 分支模型

| 分支 | 职责 | 更新方式 |
|------|------|---------|
| `master` | 稳定发布线（GitHub 默认分支） | 仅在发版时由 staging 合入，并打 `vX.Y.Z` tag |
| `staging` | 集成测试线 | 功能分支合入后在此集成验证 |
| `feature/*` | 功能开发分支 | 从 **staging** 切出 |
| `hotfix/*` | 紧急修复分支 | 从 **master** 切出 |

> 历史说明：项目早期以 `main` 为主干，2026-08-25 起废弃，请勿使用。

## 日常开发流程

1. 从 staging 切出功能分支：

   ```bash
   git switch -c feature/your-feature staging
   ```

2. 开发并提交。提交信息格式：`feat: 新功能描述` / `fix: 修复描述`

3. 完成后向 **staging** 发起 Pull Request（或经维护者合并），在 staging 上测试验证

4. 发版时将 staging 合入 **master** 并打 tag。版本号遵循语义化版本，
   发版前按 [docs/VERSIONING.md](docs/VERSIONING.md) 同步三处版本号
   （`zentray/config.py` / `pyproject.toml` / `installer/install_wizard.py`）

## 紧急修复

```bash
git switch -c hotfix/urgent-fix master
# 修复后同时合回 master 与 staging，两边都不能漏
```

热修复是唯一不经 staging 直达 master 的例外；若构成一次发布，
同样按 [docs/VERSIONING.md](docs/VERSIONING.md) 同步版本号并打 tag。

## 注意事项

- 请勿直接向 `master` 推送提交
- 请勿使用已废弃的 `main` 分支
