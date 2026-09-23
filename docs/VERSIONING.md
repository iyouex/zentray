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

见 `zentray/config.py` → `VERSION`（现为 **0.5.0**）。

## 安装包命名规范

产物目录：`dist/releases/`

| 分支 | deb 命名 | 示例 |
|------|----------|------|
| `master` | `zentray_<VERSION>_<arch>.deb` | `zentray_0.5.0_amd64.deb` |
| 功能分支 | `zentray_<VERSION>_feature-<branch>-<N>_<arch>.deb` | `zentray_0.4.2_feature-optimization-1_amd64.deb` |

说明：
- `<branch>`：当前 git 分支名，`/` 与非法字符清洗为 `-`，并去掉前缀 `feature-`
- `<N>`：该分支本机打包次序（`dist/releases/.pack_order_<branch>` 自增）
- 由 `scripts/build_package.sh` 自动生成，勿手改文件名后当正式包
