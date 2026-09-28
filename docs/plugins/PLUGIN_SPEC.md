# ZenTray 插件规范

| 字段 | 值 |
|------|-----|
| API 版本 | **1** / **2**（v2 新增触发器、任务上下文注入与结果写回） |
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
api_version: 2                    # 必填：1 | 2（triggers/write_back/params 需 2）
entry: run.sh                     # 必填，相对路径，可执行
args: []                          # 可选，追加参数（字符串数组）
workdir: .                        # 可选，相对工作目录，默认插件根
timeout_sec: 300                  # 可选，仅 script；默认 300；0=不限制（不推荐）
env:                              # 可选，额外环境变量
  FOO: bar
description: 一句话说明           # 可选
category: 网络                    # 可选，分类标签（设置页插件列表排序用）
write_back: false                 # 可选，v2：RESULT 文本写回任务备注，默认 false
triggers:                         # 可选，v2：自动触发（仅 script，见 3.3）
  - type: daily                   #   每日 HH:MM（含错过补跑）
    time: "09:00"
  - type: interval                #   每 N 分钟（1-1440，仅运行期不补跑）
    minutes: 30
  - type: cron                    #   标准 5 字段 cron（错过不补跑）
    expr: "*/15 9-17 * * 1-5"
  - type: event                   #   事件：task_done | pomodoro_end | startup
    event: task_done
params:                           # 可选，v2.1：命名入参（仅 script，见 3.5）
  - name: target
    default: "all"
    description: 作用目标
```

### 3.1 字段规则

| 字段 | 规则 |
|------|------|
| `id` | 正则 `^[a-z0-9]+(-[a-z0-9]+)*$` |
| `type` | 仅 `script` 或 `service` |
| `api_version` | 整数；接受 `1` 或 `2`；声明 `triggers`/`write_back`/`params` 必须为 `2` |
| `entry` | 相对路径；存在；Unix 上须可执行（`chmod +x`） |
| `args` | 字符串数组；**不以 shell 拼接**，argv 直传 |
| `workdir` | 相对插件根；不得 `..` |
| `timeout_sec` | 非负整数；script 超时后 terminate/kill |

### 3.2 入口可执行文件（P2）

- 可以是任意可执行文件：`bash` 脚本、二进制、带 shebang 的脚本等。  
- **推荐**用 `#!/usr/bin/env bash`（或 python）包装，便于跨环境。  
- Windows：不检查 Unix 可执行位，仅要求文件存在。  
- 应用**不会** `shell=True` 解释整行命令字符串。

### 3.3 触发器（v2，`api_version: 2`）

`triggers` 为列表，可声明多个；**仅 `script` 类型允许**（service + triggers 校验拒绝）。

| 形态 | 字段 | 语义 |
|------|------|------|
| `daily` | `time: "HH:MM"` | 每日定时；错过（关机）在下次轮询补跑一次，当日去重 |
| `interval` | `minutes: 1–1440` | 运行期每 N 分钟循环；不补跑 |
| `cron` | `expr: "分 时 日 月 周"` | 标准 5 字段；支持 `*`、`*/n`、`a-b`、`a-b/n`、列表；`7=周日`；日/周均受限时取 OR（vixie 语义）；错过不补跑 |
| `event` | `event: task_done \| pomodoro_end \| startup` | 事件触发；`task_done` 注入完成任务上下文 |

**授权（一次性）**：带触发器的插件首次自动触发前弹「允许此插件自动运行」；
允许后静默运行，拒绝则持久不再询问（设置页插件列表的授权开关可重新打开）。手动运行不受影响。

**触发跳过**：番茄钟进行中或已有脚本运行时静默跳过并记录，不产生通知。

**调度规则覆盖层（v2.1）**：设置页（🧩 插件 → 插件列表 → 展开某插件）可编辑
调度规则，保存到 `settings.json` 的 `ops.trigger_overrides`，**不改动插件文件**——
zip 重装/升级不丢自定义。优先级：覆盖层 > manifest.triggers；「恢复默认」即删除
该插件的覆盖层。覆盖层非法条目会被静默丢弃并记日志（坏数据不打断轮询）。

### 3.4 结果写回（v2，`write_back: true`）

script 插件运行结束且有任务上下文时，把 `RESULT` 文本追加写回：
任务仍在列表 → 任务备注；任务已归档 → 当日归档日志一行。

### 3.5 命名入参（v2.1，`api_version: 2`）

`params` 为列表，**仅 `script` 类型允许**（service + params 校验拒绝）。
声明顺序即 argv 顺序：

```yaml
params:
  - name: target          # 必填，同一插件内唯一
    default: "all"        # 可选，缺省值（字符串，缺省空串）
    description: 作用目标  # 可选，弹窗/设置页的输入框标签
```

实际 argv = `entry + manifest.args + [参数值...]`，参数值优先级：

**显式传入 > 参数预设 > manifest default**

- **托盘**：点击有参脚本 → 参数弹窗（预填 预设→default，可改后运行）；
  无参脚本仍走「运行前确认」开关。
- **参数预设（单组）**：设置页（插件列表 → 展开某插件）可保存每个参数的预设值，
  存 `settings.json` 的 `ops.param_presets`，不改动插件文件。
- **自动触发**：无显式入参，按 预设 > default 取值。

---

## 4. script 协议

### 4.1 调用方式

```text
<absolute-entry> [args...] [参数值...]   # v2.1：命名入参的值按声明顺序追加在 args 后
cwd = workdir 或插件根
env = 用户环境 + manifest.env + 任务上下文（v2）
```

v2 任务上下文注入（从任务页/任务完成触发运行时自动带入）：

| 变量 | 说明 |
|------|------|
| `ZENTRAY_TASK_ID` / `ZENTRAY_TASK_TITLE` | 任务 ID 与标题（有任务上下文时恒在） |
| `ZENTRAY_TASK_DETAILS` / `ZENTRAY_TASK_CATEGORY` / `ZENTRAY_TASK_PRIORITY` / `ZENTRAY_TASK_DEADLINE` | 非空才注入 |
| `ZENTRAY_TRIGGER` | 触发方式：`manual` / `daily` / `interval` / `cron` / `task_done` / `pomodoro_end` / `startup` |

### 4.2 stdout 进度协议（UTF-8，按行）

| 行格式 | 含义 | 托盘展示 |
|--------|------|----------|
| `PROGRESS <cur>/<total> <message>` | 步骤进度 | `⚡ cur/total message` |
| `LOG <message>` | 普通日志 | `⚡ message` |
| 其它非空行 | 视为日志 | `⚡ …` |
| `RESULT ok <文案>` | 结果文案（进入通知摘要/写回） | 参考 |
| `RESULT fail <原因>` | 失败原因（一票否决，见下） | 参考 |

**成败判定（v2）——两个一票否决**：

1. 进程退出码非 `0` → 失败（即使最后有 `RESULT ok`）。
2. **最后一个** `RESULT fail` → 失败（即使退出码为 `0`）。

无 `RESULT` 行时退化为纯退出码判定；`RESULT ok <文案>` 的文案会成为运行摘要
（通知、运行历史、写回文本都取它）。

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
3. 完整输出写入 `数据目录/ops_runs/<运行ID>.log`（运行ID=`<时间戳>_<pid>`），同 stem 的
   `.json` 为运行元数据（成败/摘要/触发方式/任务 ID/`run_id`/起止时间/日志路径），
   `last.json` 保留；设置页「运行历史」即读这些文件。  
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

| 来源 | 默认路径 |
|------|----------|
| 内置 | 安装包 / 仓库 `bundled_plugins/` |
| 用户 | `~/.local/share/ZenTray/plugins/`（Windows/macOS 见用户手册数据目录），目录可改 |

- v2 为**单一总开关**：设置 → 插件 → 启用后，内置与用户目录恒扫描（无分项加载开关）。  
- 校验失败：不进菜单，在设置页插件列表「校验失败」区展示。  
- **同 `id`：用户插件覆盖内置**（并打日志）。
- 分发：设置页「导入插件」支持 zip 包 / 目录两种来源（均先预览校验、通过后才能安装；
  zip 含 zip-slip 防护与 manifest 校验，安装时记录 `installed_at` 供列表按更新时间排序）。

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

- `GET /api/plugins` → `{ enabled, items: [{id,name,type,category,triggers,manifest_triggers,trigger_override,params,updated_at,write_back,authorized,...}], busy }`  
- `POST /api/plugins/{id}/run` → script 启动，body 可带 `{ "task_id": "..." }` 注入任务上下文、
  `{ "params": {name: value} }` 传命名入参（显式 > 预设 > default）；service 可 body `{ "action": "start"|"stop"|"status" }`  
- `GET /api/plugins/runs?limit=50` → 运行历史（时间倒序；v2.1 记录含 `run_id` / `started_at` / `time` 起止）  
- `GET /api/plugins/runs/log?file=<日志文件名>` → 单次运行日志内容  
- `POST /api/plugins/{id}/authorize` body `{ "allow": true|false }` → 设置自动运行授权  
- `POST /api/plugins/validate` body `{ "path": "<目录>" }` → 目录预览校验  
- `POST /api/plugins/preview-zip` body `{ "path": "<本机zip>" }` → zip 预览校验（不安装）  
- `POST /api/plugins/install` body `{ "path": "<目录>", "overwrite": false }` → 目录安装  
- `POST /api/plugins/install-zip` body `{ "path": "<本机zip>", "overwrite": false }` → zip 包安装  

---

## 9. 开发检查清单

- [ ] `plugin.yaml` 字段完整且 `api_version: 1` 或 `2`（用 triggers/write_back 则必须 2）  
- [ ] `entry` 相对路径、`chmod +x`  
- [ ] script 输出 `PROGRESS`/`LOG`，退出码正确；需要摘要时输出 `RESULT`  
- [ ] service 实现 `start`/`stop`/`status`  
- [ ] `python scripts/validate_plugin.py .` 通过  
- [ ] 用户手册 / README 若新增用户可见能力，同步更新（见仓库文档维护约定）

---

## 10. 样例

### 10.1 内置示例（随应用分发）

| 路径 | id | 说明 |
|------|-----|------|
| `bundled_plugins/net-cleanup/` | `net-cleanup` | **网络清理**：刷新 DNS/路由缓存、打印代理环境变量（Linux），api_version 1 |
| `bundled_plugins/task-report/` | `task-report` | **任务报告**：任务完成触发，回显任务上下文并 `write_back` 写回备注，api_version 2 |

启用「插件」后，托盘「🧩 插件」子菜单可见；管理入口在 **设置 → 🧩 插件**
（三大折叠块：导入插件 / 插件列表 / 运行历史）。说明见各目录 `README.md`。

### 10.2 测试夹具（仅供开发/CI）

- `tests/fixtures/plugins/sample-script`  
- `tests/fixtures/plugins/sample-service`  
- `tests/fixtures/plugins/bad-escape`（故意非法，用于校验门禁）  
- v2：`result-fail` / `result-ok-exit1` / `result-ok-text` / `env-echo`（RESULT 判定与上下文注入）
- v2.1：`param-echo`（命名入参回显，params 优先级测试）

---

## 修订记录

- **2026-09-28 插件 v2.1**（feature/plugin-v2）：①`params` 命名入参（仅 script；argv = entry + args + 参数值，优先级 显式 > 预设 > default）；②`category` 分类字段（列表排序用）；③调度规则覆盖层 `ops.trigger_overrides` 与参数预设 `ops.param_presets`（均存 settings.json，不改动插件文件）；④管理回设置页三大折叠块（导入/列表/历史），撤销独立插件中心；⑤导入统一 zip/目录切换 + 预览校验门（zip 新增 preview 端点）；⑥安装记录 `installed_at`；⑦运行元数据增 `run_id`/`started_at`；⑧托盘有参脚本弹参数弹窗（无参仍走确认开关）。
- **2026-09-28 插件 v2**（feature/plugin-v2）：①`api_version: 2`——manifest 触发器（daily/interval/cron/event）、任务上下文 env 注入、`write_back` 结果写回；②RESULT 参与成败判定（退出码与最后 RESULT fail 双一票否决），`RESULT ok <文案>` 成为运行摘要；③插件级一次性授权；④每运行落 `{时间戳}_{id}.json` 元数据，插件中心可查运行历史与日志；⑤zip 包分发（zip-slip 防护）；⑥设置改单一总开关（目录恒扫描），管理移至独立插件中心。
- **2026-09 复活适配**（feature/plugins 重上 staging）：①托盘入口改为**动态子菜单**——仅当启用且 ≥1 个插件加载成功时菜单顶部出现「🧩 插件」，未安装时保持极简菜单；②移除从未接线的 `tray_left_click` 配置项；③**服务命令不参与轮播抢占**——`service_cmd` 不再 emit `log_line`，返回 `(ok, detail)` 由调用方弹通知（修复：查询一次服务状态导致轮播永久卡死）。

