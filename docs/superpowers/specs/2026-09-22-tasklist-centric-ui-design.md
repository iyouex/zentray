# 任务列表中心化 UI 重构设计（streamline 第二轮）

日期：2026-09-22　分支：`feature/tasklist-centric-ui`（自 staging 切出，基线含 2026-08-27 streamline 与 2026-09-10/11 圆润丝滑、GSAP 动效两轮）

## 背景与目标

上一轮 streamline 新增的托盘"当前任务"入口（`/tasks/:id/action` 操作选择页）与任务列表右栏功能大量重叠；任务列表本身存在四个痛点：①进度更新必须跳转 Progress 页；②右栏"详情"仅 5 项 meta；③周期模板管理是独立页面，与列表割裂；④周期模板无法暂停或跳过。本轮目标：**任务列表成为唯一任务中枢**——所有任务编辑与状态流转经列表完成。

边界：番茄钟本轮不动；完成/废弃后留在列表刷新（不再关窗）。

## 设计一：托盘菜单取消"当前任务"入口

- 菜单 6→5 项，删 `current_task` 项；`CurrentTaskCommand` 及死代码（`TaskActionCommand`/`task_action_` 动态前缀/`ProgressCommand`/`PeriodicManageCommand`，均不在 COMMAND_MAP 或无发射方）一并清理。
- "切换到此任务"保留在列表右栏（`POST /api/tasks/{id}/select` → `closeHost({action:'select'})` 回托盘闭环不变，番茄钟的当前任务依赖由此满足）。
- `_dispatch_task_action` 与 Qt 回退对话框保留（`ZENTRAY_UI=qt` 路径仍用）。

## 设计二：任务列表头部与构成筛选

- 头部：左=标题+主按钮"新建"（周期视图下变"新建周期任务"，query `mode=periodic`，恒带 `from=list`）；右=X 纯图标关窗钮；删"周期任务"按钮。
- 分类 chips 之上加构成筛选行：`全部 / 一次性 / 周期`（复用 `.fchip` 与 aria-pressed 模式，切换走既有 Flip）。与分类 chips 两层 AND。
- **周期视图混排**：活跃周期实例 + 休眠模板（无活跃实例的模板，置灰虚线 `.dormant`，meta 显示 `每N天/周/月 · 下次派发`或`已暂停`）。全部视图不含休眠模板（避免同任务两形态）。
- 条目统一 `{key: 't:'+id | 'm:'+template_id, kind}`；Flip 靠 key 前缀隔离，`celebrateCard` 按 `data-task-id` 找卡、模板卡不带自然跳过。

## 设计三：右栏详情补全与内联进度

- 实例态补全：details（3 行 clamp）、提醒开关+时间点摘要、周期来源标签+"编辑模板"链接（`?template=1`）、"逾期自动废弃"标签、最近 3 条进度日志。
- 内联进度：`a-slider` 0-100 step 10 + 备注 + "记录"→ 现有 `POST /api/tasks/{id}/progress`；100% 庆祝。删 Progress.vue 与路由。
- 模板态操作集：编辑模板 / 暂停恢复（现有 PUT）/ 跳过接下来 N 次（1-30，新端点）/ 删除模板（文案沿用"已生成的实例不会自动删除"）。
- 完成/废弃：`celebrateCard` 后清空选中并 `reload()` 留页。
- 窗口 900×540 → 960×600。

## 设计四：周期模板暂停/跳过（后端）

- `PeriodicTemplate.paused: bool`（经 PUT 写入；`_template_from_data` 白名单需同步读取，否则 PUT 丢字段）。
- `period_key` 拆 `_bucket_index`/`_key_from_bucket`；新增 `parse_period_key`；**`should_spawn` 改有序比较**（原 `!=` 语义下水位领先会误派发）：`paused` → False；水位桶 ≥ 当前桶 → False；前缀不同/解析失败 → True（与现状一致）。两处派发路径（task_service / watcher）都经 `should_spawn`，判断自动双路径生效。
- `advance_period_key(..., n)`：桶序号 +n。**跳过语义：始终恰好跳过接下来 N 个未派发的桶**（当前桶已派发→第 N+1 桶恢复；未派发→含当前桶共 N 个）。
- `next_spawn_date(tmpl, today)`：日步进找首个 `should_spawn`（上限 400 天；`ponytail: interval>13 月时再改桶算术`）；经 `_template_dict` 注入所有模板端点——**前端不自算桶逻辑**。
- `build_due_instance(tmpl, today)`：到期则构造实例并推进水位；两处派发体收敛到它（单测覆盖双路径）。
- `skip_template(id, count)`：原地推进水位持久化（不走 `_template_from_data`，不触发派发）；新端点 `POST /api/templates/{id}/skip`，count 钳 1..52。

## 边界语义

- **恢复**：unpause 后 watcher 下一轮（≤60s）为当前桶派 1 个，不回填历史。暂停/恢复按钮 tooltip 写明。
- **跳过计数**："从今天起 N 个未派发桶"；休眠模板上 N=1 含今天。
- **休眠判定分歧**（前端"无活跃实例" vs 后端"水位"）：展示统一用后端 `next_spawn_date`，与派发行为天然一致。

## 删除清单

TaskAction.vue / Progress.vue / Periodic.vue 及其 3 条路由；`try_vue_task_action`/`try_vue_progress`/`try_vue_periodic`；`CurrentTaskCommand` 与上述死命令；菜单 `current_task` 项。`from=list` 返回逻辑保留（TaskForm 仍需）。

## 测试与验证

- test_periodic 新增：advance/有序水位/next_spawn_date/build_due_instance；test_task_service 新增：skip_template 推进水位不产实例、PUT 后 paused 不丢；watcher 直调 `_do_maintenance` 断言 paused 模板不派发；test_menu_builder 更新为 5 项。
- 手测：构成筛选 Flip 混排；暂停后 60s 无新实例；跳 2 次下次派发后移 2 桶；滑条+备注落库；完成/废弃不关窗；`ZENTRAY_UI=qt` 回退正常。

## 实施顺序

0. 在途窗口生命周期工作先行落盘；ui-streamline 快进合入 staging 后切分支（已完成）。
1. `feat(periodic)` 后端暂停/跳过 + 单测。
2. `refactor(menu)` 移除当前任务入口并清理死命令。
3. `feat(web)` 列表为中心重组 + `npm run build` dist 成对入库。
