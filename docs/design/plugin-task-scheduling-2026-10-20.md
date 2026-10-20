# 插件随任务调度重设计（/plan 2026-10-20）

> 用户裁定：插件删除**全部**自身调度功能与调度参数/选项，只保留运行时参数；
> 此后插件脚本一律**随所关联任务的调度**运行——调度参数在任务上设置或跟随
> 任务；插件简介一并删除。依赖[时间体系重设计](task-time-redesign-2026-10-20.md)
> 落地后的弹窗机制（popup_at_due + 额外弹窗行，实现顺序在其后）。

## 1. 新模型一句话

**插件唯一的自动触发源 = 所关联任务的弹窗时刻**；无关联任务的插件仅手动运行
（插件面板 ▶ / 任务编辑页 ▶）。定时（daily/interval/cron）与事件（task_done/
pomodoro_end/break_end/startup）自动触发**全部退役**——树内四脚本插件均为
daily 型，无 event 型用户，删除不断档。

- 触发点：任务任一弹窗时刻到点（截止弹窗 popup_at_due 或额外弹窗时间行，
  60s 窗 + fired 持久去重 + 跳过公休日门控**全部沿用时间体系机制，零新增状态**）
  且 `task.plugin_id` 非空 → `runtime.run_script(plug, task=task, trigger="task_popup")`，
  运行入参取参数预设（预设属运行时，保留）。弹窗本身照常弹出，插件并行运行。
- busy/番茄中：沿用现状静默跳过（一行 logger，不再持久 last_skip）。
- 授权三态机制删除：**把插件关联到任务即显式授权**（用户主动行为）。

## 2. 删除清单

### 后端
| 位置 | 动作 |
|---|---|
| `zentray/plugins/triggers.py` | **整文件删**（477 行：轮询 worker、四型触发、period 推导、水位/补跑、授权、事件分发）；busy/番茄守卫 5 行移入 reminder_job 触发处 |
| `zentray/workers/plugin_trigger.py` | 删（QThread 每分钟轮询不再存在） |
| `zentray/main.py` | 删 worker 启动、`on_plugin_authorize` 槽、`migrate_legacy_jobs()` 调用、`dispatch_event("startup")` |
| `zentray/services/task_service.py` | 删 `_dispatch_plugin_event` 挂点 ×2 |
| `zentray/ui/controller.py` | 删 pomodoro_end / break_end 事件分发 ×2 |
| `OpsSettings.trigger_overrides` | 字段删（盘上残键忽略；param_presets / plugin_notify_channels 保留） |
| `plugin_triggers.json` | 不再读写（迁移标记复用一次后停用，见 §4） |
| `plugins/models.py` / loader | TriggerType/manifest triggers 解析删；**携带 triggers/description 的旧 manifest 容忍不报错** |

### 插件本体（bundled_plugins）
朝闻/暮省：删 `triggers:` 块与 6 个调度参数（period/time/weekday/day_of_month/
skip_weekends/skip_holidays）、删 `description`；保留 save_local 与 AI 风格类运行参数。
ai-news-digest / email-digest 同理（triggers + description）。周期/时刻/跳过公休日
改由关联任务承载。

### 前端
| 位置 | 动作 |
|---|---|
| Settings-插件 已安装行 | 删「自动运行提示（⏱ …）」与简介一句 |
| Settings-插件 展开面板 | 删「自动运行授权」块与 trigLabel；删「简介」编辑输入（名称编辑保留） |
| PluginsPanel 卡片 | 删自动运行提示行与简介 |
| 说明抽屉 | 删简介段；参数表/README 保留 |
| TaskForm 关联插件 | 选项只显示名称；加一行 hint：「关联后，插件在本任务的每个弹窗时刻自动运行」 |

## 3. 任务侧承接（调度参数的唯一去处）

不新增任何插件侧调度字段。完整表达 = `Task.plugin_id`（含周期模板，派发继承，
现状已有）+ 时间体系四要素（开始时间 / 截止+due_time / 弹窗行 / 跳过公休日）：
- 朝闻 08:00 日计划 → 日周期模板，弹窗行 08:00，关联 chaowen
- 周报 digest → 周周期模板周一 09:00 弹窗，关联对应插件
- 模板的弹窗行/due 随派发继承到实例（时间体系已定），实例到点即触发

interval/cron 需求一律建模为任务的弹窗行（分钟级 interval 无树内用户，不保留）。

## 4. 存量迁移（一次性，最小）

朝闻/暮省是仅有的带调度存量（v0.7.14 刚迁移过一轮）：启动时若
`plugin_triggers.json` 存在且未标记迁移 → 按两插件**参数预设**各建一条周期任务
（period→周期类型、time→弹窗时刻、skip_weekends/skip_holidays→跳过公休日、
标题=插件名、plugin_id 关联、弹窗行=旧 time），随后在文件内打迁移标记停读。
无预设/文件缺失则跳过；幂等。其余插件（含用户目录自定义）由用户手动建关联任务。

## 5. 测试点

1. 弹窗时刻到点 + plugin_id → run_script(trigger="task_popup", task)；busy/番茄静默
2. 无 plugin_id 不触发；fired 去重后弹窗不重弹 ⇒ 插件不重跑
3. 跳过公休日联动（弹窗静默日插件同静默）
4. 迁移：按预设建任务一次、幂等、无预设不建
5. OpsSettings 旧 trigger_overrides 残键忽略；manifest 携带 triggers/description 容忍
6. `test_job_plugins.py` 中 period 推导/补跑/授权用例改写为上述新语义

## 6. 文档

USER_MANUAL 插件章：调度三规则表 →「随任务调度」一节（触发规则一句话 + 建任务
示例）；朝闻/暮省段参数表删调度项；设置页插件行描述精简。README 插件行、
AI-FEATURES 现状注、docs/plugins/* 同步。

## 7. 风险与边界

- 强依赖时间体系重设计合入（弹窗行继承/fired 机制），实现排在其后
- 用户目录第三方插件若用 interval/cron/event 触发将失去自动运行（按裁定接受，
  手册注明手动/关联任务两条路）
- 授权删除后，「关联任务」成为唯一授权面——误关联会在弹窗时刻跑脚本，风险低
  （关联是显式选择）且弹窗可见
- ai-news-digest / email-digest（用户自装于 ~/.local/share）升级后需自建关联任务，
  迁移只覆盖内置朝闻/暮省
