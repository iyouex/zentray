# ZenTray 插件规范

| 字段 | 值 |
|------|-----|
| API 版本 | **1**（`api_version: 1`） |
| 校验命令 | `python scripts/validate_plugin.py <插件目录>` |

本文是**插件作者与合入门禁**的权威说明。不符合规范的插件**不会**出现在托盘菜单。

---

## 1. 目标与边界

ZenTray 提供 **插件运行时**（托盘「插件」入口、进度抢占任务轮播、设置开关）。  
具体业务（VPN、代理、邮箱、清缓存等）由**插件**实现，不写进核心。

| 类型 | 用途 | 执行特点 |
|------|------|----------|
| `script` | 一次性流程 | 可长时间运行；stdout 进度；**抢占**任务轮播 |
| `service` | 可启停进程/守护 | `start` / `stop` / `status`；不长期抢占轮播 |

---

## 2. 目录结构

```text
my-plugin/
  plugin.yaml          # 必填：清单
  run.sh               # 示例入口（任意可执行文件，见 entry）
  README.md            # 建议：用途、依赖、权限
  # 可选：资源文件、子目录（须在插件根内）
```

- 插件根目录名可任意；**身份以 `plugin.yaml` 的 `id` 为准**。  
- 入口文件必须在插件根**之内**，禁止 `..` 与绝对路径。

---

## 3. plugin.yaml 字段

```yaml
id: sample-script                 # 必填，唯一
name: 示例脚本                    # 必填，菜单显示名
version: 0.1.0                    # 必填
type: script                      # 必填：script | service
api_version: 1                    # 必填，目前仅 1
entry: run.sh                     # 必填，相对路径，可执行
args: []                          # 可选，追加参数（字符串数组）
workdir: .                        # 可选，相对工作目录，默认插件根
timeout_sec: 300                  # 可选，仅 script；默认 300；0=不限制（不推荐）
env:                              # 可选，额外环境变量
  FOO: bar
description: 一句话说明           # 可选
```

### 3.1 字段规则

| 字段 | 规则 |
|------|------|
| `id` | 正则 `^[a-z0-9]+(-[a-z0-9]+)*$` |
| `type` | 仅 `script` 或 `service` |
| `api_version` | 整数；运行时仅接受 `1` |
| `entry` | 相对路径；存在；Unix 上须可执行（`chmod +x`） |
| `args` | 字符串数组；**不以 shell 拼接**，argv 直传 |
| `workdir` | 相对插件根；不得 `..` |
| `timeout_sec` | 非负整数；script 超时后 terminate/kill |

### 3.2 入口可执行文件（P2）

- 可以是任意可执行文件：`bash` 脚本、二进制、带 shebang 的脚本等。  
- **推荐**用 `#!/usr/bin/env bash`（或 python）包装，便于跨环境。  
- Windows：不检查 Unix 可执行位，仅要求文件存在。  
- 应用**不会** `shell=True` 解释整行命令字符串。

---

## 4. script 协议

### 4.1 调用方式

```text
<absolute-entry> [args...]
cwd = workdir 或插件根
env = 用户环境 + manifest.env
```

### 4.2 stdout 进度协议（UTF-8，按行）

| 行格式 | 含义 | 托盘展示 |
|--------|------|----------|
| `PROGRESS <cur>/<total> <message>` | 步骤进度 | `⚡ cur/total message` |
| `LOG <message>` | 普通日志 | `⚡ message` |
| 其它非空行 | 视为日志 | `⚡ …` |
| `RESULT ok` | 可选结果文案 | 参考 |
| `RESULT fail <reason>` | 可选失败原因 | 参考 |

**成功判定以进程退出码为准：`0` 成功，非 0 失败**（即使出现 `RESULT ok`）。

### 4.3 示例 `run.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "PROGRESS 1/2 准备"
echo "LOG doing work"
# ... 你的逻辑 ...
echo "PROGRESS 2/2 完成"
echo "RESULT ok"
exit 0
```

### 4.4 托盘行为

1. 启动后停止任务轮播推进，显示进度文案（约 50 字截断）。  
2. 结束后系统通知 + 恢复任务轮播。  
3. 完整输出写入 `数据目录/ops_runs/<时间>_<id>.log`，摘要 `ops_runs/last.json`。  
4. 与番茄钟**互斥**（运行中不可互相启动）。

---

## 5. service 协议

同一 `entry`，**第一个参数**为动作：

```bash
./entry start
./entry stop
./entry status
```

| 动作 | 约定 |
|------|------|
| `start` | 启动服务；退出码 0 表示已触发成功 |
| `stop` | 停止服务；退出码 0 表示已触发成功 |
| `status` | stdout **首行**（trim）优先为 `running` \| `stopped` \| `unknown`；否则回退退出码 0=running、非 0=stopped |

菜单结构：服务名 → 启动 / 停止 / 状态。

---

## 6. 校验与「符合才应用」

### 6.1 本地 / CI

```bash
python scripts/validate_plugin.py path/to/plugin
# 可多路径；任一失败则 exit 1
```

检查项包括：YAML 结构、字段、路径逃逸、entry 存在与可执行性等。

### 6.2 加载位置

| 来源 | 默认路径 | 设置项 |
|------|----------|--------|
| 内置 | 安装包 / 仓库 `bundled_plugins/` | 加载内置插件 |
| 用户 | `~/.local/share/ZenTray/plugins/`（Windows/macOS 见用户手册数据目录） | 加载用户插件 + 目录可改 |

- 仅当 **设置 → 插件 → 启用** 时扫描。  
- 校验失败：不进菜单，写日志。  
- **同 `id`：用户插件覆盖内置**（并打日志）。

### 6.3 合入 `bundled_plugins/`

1. 通过 `validate_plugin.py`。  
2. 提供 README（依赖、权限、是否需 root）。  
3. 不提交密钥、内网专属 token。  
4. 建议附最小自测说明（不必真连公司 VPN）。

---

## 7. 安全注意

- 插件以**当前用户**权限运行；需管理员时插件自行 `pkexec`/`sudo`（应用不代填密码）。  
- 勿在插件中硬编码密钥；用环境变量或本机安全配置。  
- 默认「执行前确认」可降低误点风险。  
- 不信任来源的插件视为任意代码执行，仅安装可信插件。

---

## 8. 任务关联插件

任务字段 `plugin_id`（可选）保存插件 `id`。

| 场景 | 行为 |
|------|------|
| 新建 / 编辑任务 | 下拉选择已加载插件；可清空 |
| 更新进度页 | 若已关联，显示「▶ 运行关联插件」 |
| 周期模板 | 模板可带 `plugin_id`，派发实例时继承 |

API：

- `GET /api/plugins` → `{ enabled, items: [{id,name,type,...}], busy }`  
- `POST /api/plugins/{id}/run` → script 启动；service 可 body `{ "action": "start"|"stop"|"status" }`  

---

## 9. 开发检查清单

- [ ] `plugin.yaml` 字段完整且 `api_version: 1`  
- [ ] `entry` 相对路径、`chmod +x`  
- [ ] script 输出 `PROGRESS`/`LOG`，退出码正确  
- [ ] service 实现 `start`/`stop`/`status`  
- [ ] `python scripts/validate_plugin.py .` 通过  
- [ ] 用户手册 / README 若新增用户可见能力，同步更新（见仓库文档维护约定）

---

## 10. 样例

### 10.1 内置示例（随应用分发）

| 路径 | id | 说明 |
|------|-----|------|
| `bundled_plugins/net-cleanup/` | `net-cleanup` | **网络清理**：刷新 DNS/路由缓存、打印代理环境变量（Linux） |

启用「插件」并打开 **加载内置插件** 后，菜单中可见「网络清理（示例）」。  
说明见该目录 `README.md`。

### 10.2 测试夹具（仅供开发/CI）

- `tests/fixtures/plugins/sample-script`  
- `tests/fixtures/plugins/sample-service`  
- `tests/fixtures/plugins/bad-escape`（故意非法，用于校验门禁）

---

## 修订记录

- **2026-09 复活适配**（feature/plugins 重上 staging）：①托盘入口改为**动态子菜单**——仅当启用且 ≥1 个插件加载成功时菜单顶部出现「🧩 插件」，未安装时保持极简菜单；②移除从未接线的 `tray_left_click` 配置项；③**服务命令不参与轮播抢占**——`service_cmd` 不再 emit `log_line`，返回 `(ok, detail)` 由调用方弹通知（修复：查询一次服务状态导致轮播永久卡死）。

