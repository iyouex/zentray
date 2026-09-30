# ZenTray 版本号规则

从 **0.1.0** 起采用语义化版本 `MAJOR.MINOR.PATCH`：

| 变更类型 | 版本怎么加 | 示例 |
|----------|------------|------|
| **修 Bug / 优化 / 小功能**（修复、打磨、局部小能力、存量功能移植复活、脚本与打包改进） | `PATCH + 0.0.1` | 0.6.1 → **0.6.2** |
| **大功能迭代**（里程碑级新模块/新体系，改变产品使用方式） | `MINOR + 0.1.0`，PATCH 归零 | 0.6.9 → **0.7.0** |
| **架构重构 / 大改版** | `MAJOR + 1.0.0`，MINOR/PATCH 归零 | 0.9.3 → **1.0.0** |

**判级原则：拿不准一律 PATCH，从保守。** 只有当一批变更是「用户能明确感知的成体系新能力」
（例如：番茄钟、AI 计划/复盘、备份体系这类产品级模块首次成型）才动 MINOR；日常修复与
小功能增强永远 PATCH 累加，多条同发也只加一次。（2026-09-28 订正：插件功能复活 + 打包/
卸载可靠性修复曾误判为 MINOR 发 0.7.0，回退为 0.6.2）

## 唯一真相源

- 运行时版本：`zentray/config.py` 中的 `VERSION`
- 打包/元数据：`pyproject.toml` 的 `version`（应与 `VERSION` 同步）

发版前检查两者一致。

## 当前版本

见 `zentray/config.py` → `VERSION`（现为 **0.6.3**）。

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
