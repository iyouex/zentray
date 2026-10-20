# 任务时间体系重设计（/plan 2026-10-20）

> 用户裁定：v0.7.14 后任务表单时间控件太乱没有条理（截止日期 / 开始提醒时间 /
> 关键交付时间三处分散、交付时间兼职截止语义混乱）。按四条设想重新设计。

## 1. 信息架构：一个分组、四个可选项

任务表单（新建/编辑、一次性/周期模板统一）收敛为单一「⏰ 时间与提醒」分组，
全部**勾选后才可设置**（与现有 checkbox 模式一致），行序即重要性：

```
⏰ 时间与提醒
├─ ☐ 开始时间    未勾选 = 创建/派发后立即开始（现状即时语义）
├─ ☐ 截止时间    未勾选 = 无截止、永不逾期
├─ ☐ 弹窗提醒    勾选后默认在「截止时刻」弹窗；可再添加多个弹窗时间
└─ ☐ 跳过公休日  新建按一级分类预设带出（v0.7.14 现状不变）
```

## 2. 默认值矩阵（勾选瞬间预填，均可改）

时分默认取**一级分类提醒时间窗**（设置 → 任务，v0.7.14 已有字段
`remind_window_enabled/start/end`）；未启用则为 00:00 / 23:59。

### 开始时间

| 任务类型 | 日期部分默认 | 时分默认 |
|---|---|---|
| 一次性 | 当天 | 窗口起点（如 09:00）；未设 00:00 |
| 日周期模板 | 每天（无需日期槽，仅时分） | 同上 |
| 周周期模板 | 每周一（slot weekday=0） | 同上 |
| 月周期模板 | 每月 1 号（slot day_of_month=1） | 同上 |

- 存储：一次性 = `remind_start`（ISO datetime，现状字段）；周/月 = 现状
  `remind_start_slots`（weekday/dom + time_of_day）；日模板 = 新增仅时分
  （`remind_start_slots` 加 daily 用法：单 slot 只看 time）。
- 解析复用 `resolve_remind_start`（已过=即时，周期内首个匹配日）。

### 截止时间

| 任务类型 | 日期部分默认 | 时分默认 |
|---|---|---|
| 一次性 | 当天 | 窗口终点（如 18:00）；未设 23:59 |
| 日周期模板 | 每天（派发日当天） | 同上 |
| 周周期模板 | 每周日（`deadline_weekday=6`） | 同上 |
| 月周期模板 | 每月底（`deadline_day_of_month=31`，派发时天然钳到当月月末） | 同上 |

- `deadline` 保持 **YYYY-MM-DD 不动**（日历全天事件/派发/归档全链路不破坏）；
  新增 `due_time`（HH:MM）承载时分，`None` = 按 23:59 语义。
- 模板的 `deadline_weekday` / `deadline_day_of_month` 字段模型已有、
  **表单从未暴露**——本次补上 UI（周下拉周一~周日、月下拉 1~31 号）。
- 周期模板新增 `due_time`，派发实例继承（同 remind_start/skip_holidays 链路）。

### 弹窗提醒

- 勾选 = `popup_at_due=true`：**截止时刻**（deadline + due_time，缺省 23:59）
  到点弹窗一次；改截止/时分即改弹窗时刻，无需手动同步。
- 「➕ 添加弹窗时间」= 现有 `deliveries[]` 列表追加行（日期+时分），各自
  到点弹、`fired` 持久去重（v0.7.14 机制照用）；行内不再暴露 notify 勾选
  （加进列表即弹，后端兼容读旧 notify=false 行为）。
- **退役 v0.7.14「最晚交付=截止」推导**：截止只由截止行决定；旧任务的
  deadline 在保存时已物化，去掉推导不影响存量。

## 3. 数据模型变更（最小集）

| 位置 | 变更 |
|---|---|
| `Task` | + `due_time: Optional[str]`、+ `popup_at_due: bool=False`；`deliveries` 语义改「额外弹窗时间」 |
| `PeriodicTemplate` | + `due_time`、+ `popup_at_due`（派发继承）；补 deadline_weekday/day_of_month 表单暴露 |
| `reminder.py` | `due_popup_at(task, now)`（popup_at_due 且未 fired → 截止时刻入 60s 窗）；删 `deliveries_deadline` |
| `task_service.py` | 删「最晚交付覆盖截止」；逾期判定：有 due_time 分钟级、无则日级（现状） |
| `reminder_job.py` | 弹窗队列 = due 弹窗 + deliveries 各行（同一 fired 机制，due 用 key `"due"`） |
| `calendar_feed.py` | ⏱ 事件投影源从 deliveries 改为「due 时刻 + 弹窗时间行」（逻辑同形） |

分类预设（窗口起止/跳过公休日）、轮播三重门控（开始/窗口/公休日）**零改动**。

## 4. 行为语义速查

| 场景 | 行为 |
|---|---|
| 未勾开始 | 立即进入轮播（remind_start=None 现状） |
| 未勾截止 | 无逾期、日历无截止事件 |
| 勾弹窗但未勾截止 | 弹窗行仅由「添加弹窗时间」提供（无 due 弹窗） |
| 截止+due_time 已过 | 任务逾期（分钟级）；popup_at_due 的弹窗照弹一次（逾期提示性质） |
| 跳过公休日 | 弹窗与轮播当日整体静默（现状门控） |

## 5. 迁移与文档

- 存量兼容：deliveries 旧行照弹；deadline 已物化；无 schema 破坏。
- 手册「提醒体系（三分）」段落改写为「时间四要素」；README 任务行同步；
  日历段 ⏱ 措辞微调。

## 6. 测试点

1. 默认值矩阵：各任务类型勾选瞬间预填（一次性/日/周/月 × 开始/截止），
   分类窗口开/关两态
2. due 弹窗：到点一次、fired 去重、改 due_time 换时刻
3. 逾期粒度：有/无 due_time
4. 模板派发继承 due_time/popup_at_due；月底 31 钳制（2 月）
5. 删除最晚交付推导后存量任务 deadline 不变
