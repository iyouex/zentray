# ZenTray 版本号规则

从 **0.1.0** 起采用语义化版本 `MAJOR.MINOR.PATCH`：

| 变更类型 | 版本怎么加 | 示例 |
|----------|------------|------|
| **优化 / 修 Bug** | `PATCH + 0.0.1` | 0.1.0 → **0.1.1** |
| **功能迭代**（新能力、交互增强） | `MINOR + 0.1.0`，PATCH 归零 | 0.1.3 → **0.2.0** |
| **项目重构 / 大改版** | `MAJOR + 1.0.0`，MINOR/PATCH 归零 | 0.3.2 → **1.0.0** |

## 唯一真相源

- 运行时版本：`zentray/config.py` 中的 `VERSION`
- 打包/元数据：`pyproject.toml` 的 `version`（应与 `VERSION` 同步）

发版前检查两者一致。

## 当前版本

见 `zentray/config.py` → `VERSION`（现为 **0.6.1**）。

## 安装包命名规范

产物目录：`dist/releases/`。**包版本始终跟随程序主版本（`VERSION`），不随构建递增**；同版本多次构建靠分支后缀 + 打包次数区分。

| 分支 | deb 命名 | Debian Version | 示例 |
|------|----------|----------------|------|
| `master` | `zentray_<VERSION>_<arch>.deb` | `<VERSION>` | `zentray_0.6.1_amd64.deb` |
| 其它分支（含 staging、feature/*） | `zentray_<VERSION>+<branch>.<N>_<arch>.deb` | 同文件名版本串 | `zentray_0.6.1+staging.4_amd64.deb` |

说明：
- `<branch>`：当前 git 分支名，`/` 与非法字符清洗为 `.`（Debian 版本串仅允许字母数字与 `. + ~`）
- `<N>`：该分支本机打包次序（`dist/releases/.pack_order_<branch>` 自增）
- 后缀必须进 Debian Version 字段：分支包若与 master 同名，apt 视同版本拒绝覆盖安装，装完仍是旧程序（历史踩坑）
- **来源追溯**：打包时在 `DEBIAN/control` 写入 `X-ZenTray-Branch` / `X-ZenTray-Commit`，`dpkg-deb -I <包>` 即可查构建分支与提交；无法确定分支（分离 HEAD）时打包直接中止
- 由 `scripts/build_package.sh` 自动生成，勿手改文件名后当正式包
