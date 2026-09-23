# ZenTray UI 优化设计:托盘菜单精简 + 弹窗交互统一

日期:2026-08-27
状态:已与用户确认设计方向(菜单方案 A、窗口形态「保留标题栏去按钮」、出口行为跟随来源)

## 背景与目标

1. **无损精简托盘下拉菜单,合并冗余入口**:现有 9 个顶层菜单项中,「更新进度」「编辑查看」与任务列表页内操作完全重复,「新建任务」「周期任务管理」在任务列表页内可达。合并后顶层降至 6 项,所有原功能仍可达。
2. **统一所有弹窗交互**:所有弹窗固定窗口大小、去掉右上角系统操作按钮(最大/最小化/关闭),仅依靠页内「确定/取消」按钮控制页面的关闭与返回。

## 现状要点(设计依据)

- 托盘菜单:`zentray/ui/menu_builder.py` 构建条目列表 → `tray.py`(Linux AppIndicator 桥 / Qt 回退)渲染,两后端均支持 `separator` / `submenu` / `enabled`。
- 弹窗 = `zentray/ui/web_host.py::VueDialog`(QDialog 包 QWebEngineView)优先;`ZENTRAY_UI=qt` 或无 WebEngine/dist 时回退 6 个 Qt 对话框(dialogs.py / task_list_dialog.py / settings_dialog.py / periodic_manager.py / reminder_dialog.py / setup_wizard.py)。
- 全部 11 个 Vue 页面已具备页内出口按钮并走 `zentray://close` 协议(`web/src/api/client.js::closeHost/cancelHost`)回传结果。
- 现存交互断裂:任务列表页内 `$router.push` 跳到 新建/编辑/进度 后,子页「取消/保存」直接关窗而非返回列表。
- `menu_builder.build_main_menu` 的既有约束:菜单结构不依赖轮播当前标题,避免轮播时整菜单重建闪动。

## 设计一:托盘菜单精简(9 项 → 6 项)

### 新结构

```
📌 当前任务          ← 合并原「更新进度」+「编辑查看」
📋 任务列表          ← 页内已有「新建」,新增「周期任务」入口
─────────────
🍅 专注 N 分钟        ← 番茄进行中变为:⏹ 中止专注 + ⏱ 延长 M 分钟
─────────────
🔧 扩展按钮(如有,保持现状位置)
─────────────
📜 历史记录
⚙️ 设置
❌ 退出程序
```

### 改动点

- `menu_builder.build_main_menu()`(`zentray/ui/menu_builder.py:24`):
  - 新增 `{"id": "current_task", "label": "📌 当前任务", "enabled": task_exists and not is_pomodoro}`;label 保持静态,不显示轮播任务名(避免菜单重建闪动)。
  - 删除 `progress` / `edit` / `new` / `periodic_manage` 四个顶层条目。
  - `pomodoro_minutes` / `extend_minutes` 参数与番茄分支逻辑不变;扩展按钮区不变。
- `commands.py`(`zentray/ui/commands.py`):
  - 新增 `CurrentTaskCommand`:取轮播当前任务 → 复用现有 `try_vue_task_action()`(打开 `/tasks/:id/action`,页内含 切换/进度/编辑/完成/废弃/取消)→ 回退 `TaskActionDialog`。零新页面、零新路由。
  - `COMMAND_MAP` 删除顶层 `progress` / `edit` 映射;`_run_progress_dialog` / `try_vue_edit_task` 保留(action 页内动作仍调用)。
- `web/src/views/TaskList.vue`:页头新增「🔁 周期任务」按钮 → `$router.push({path:'/periodic', query:{from:'list'}})`。

### 无损核对表

| 原入口 | 新路径 |
|---|---|
| 更新进度 | 📌 当前任务 → action 页 → 更新进度 |
| 编辑查看 | 📌 当前任务 → action 页 → 编辑 |
| 完成当前任务(曾为内部命令) | 📌 当前任务 → action 页 → 完成 |
| 新建任务 | 📋 任务列表 → 新建(已有) |
| 周期任务管理 | 📋 任务列表 → 周期任务(新增) |
| 任务列表 / 专注·中止·延长 / 历史 / 设置 / 退出 | 顶层直达,不变 |

## 设计二:弹窗窗口层统一

### VueDialog(`zentray/ui/web_host.py:58`)

- 窗口标志(非 frameless 分支):
  ```python
  flags = Qt.CustomizeWindowHint | Qt.WindowTitleHint  # 保留标题栏,无任何系统按钮
  ```
  替代现有 `Dialog` 默认标志;quick-add 的 frameless 分支保持现状。
- 尺寸:`setFixedSize(width, height)` 替代 `fit_dialog()`;保留 `center_dialog()` 居中。小屏保护:固定值取 `min(width, 0.92 × 屏幕可用宽/高)`,防 1366×768 溢出。
- 无 WebEngine / 无 dist 的 QLabel 降级分支同样应用该标志与固定尺寸。
- 各路由固定尺寸沿用 `vue_commands.py` 现有值(如 settings 920×600、history 980×660、progress 440×320),内容超长由页内滚动承担(Settings/History 已有 overflow: auto)。

### Qt 回退对话框

`dialog_utils.py` 新增统一 helper(单一事实来源):

```python
def apply_dialog_chrome(dialog, *, width, height):
    """统一弹窗形态:去系统按钮(CustomizeWindowHint|WindowTitleHint)+ setFixedSize + 居中。"""
```

6 个 Qt 对话框各自现有的 `fit_dialog(...)` 调用替换为 `apply_dialog_chrome(..., width=当前 preferred_w, height=当前 preferred_h)`。所有对话框已具备页内出口按钮(向导有「跳过全部」、提醒有「关闭本次」),无卡死风险。SettingsDialog 大页面靠现有 `make_scroll_body` 内部滚动。

### 前端出口改造:行为跟随来源

**规则:一级页面出口 = 关窗;二级页面出口 = 返回上级并刷新。**

- `TaskList.vue` 三处跳转(新建/进度/编辑)与新增的周期入口,统一携带 `query: {from: 'list'}`。
- `TaskForm.vue` / `Progress.vue` / `Periodic.vue` 检测 `route.query.from === 'list'`:
  - 「取消」→ `$router.back()` 返回列表,不关窗;
  - 「保存 / 完成 / 废弃」→ 执行后同样返回列表并触发列表刷新(可继续操作下一个任务);
  - 无 `from=list`(托盘直达)→ 行为不变,`closeHost` 关窗。
- 「📌 当前任务」action 页为托盘专属一级页,保持「选完操作即关窗」。
- 返回后列表刷新:已确认 `App.vue` 的 `<router-view />` 无 keep-alive,返回时 TaskList 重挂载、`onMounted(reload)`(`TaskList.vue:128`)自动触发,无需额外刷新代码。

## 边界语义

| 路径 | 行为 | 理由 |
|---|---|---|
| Esc 键 | 保留 = 取消(reject,payload cancelled) | 键盘可达性最佳实践;QuickAdd 文案本就注明「ESC 取消」 |
| Alt+F4 / WM 关闭 | 保留 = 取消兜底 | 彻底拦截会制造「关不掉的窗口」(前端异常时死锁);WM 层面无法真禁 |
| quick-add 闪电添加 | 不动 | 已是 frameless + 固定尺寸 + 置顶,即目标形态 |
| Reminder 弹窗 | 应用统一形态,保留 stay_on_top | 置顶与去按钮正交 |

## 测试与验证

- 新增 `tests/unit/test_menu_builder.py`:
  - 6 项结构断言(顶层 id 顺序);
  - `current_task` / `task_list` 的 enabled 矩阵(有无任务 × 番茄中否);
  - 番茄进行中变体(⏹ 中止 + ⏱ 延长)、空闲变体(🍅 专注 N 分钟);
  - 扩展按钮插入位置。
- 手动验证清单(窗口形态依赖 QApp/桌面环境,无单测条件):
  - 11 个 Vue 路由逐个打开:①右上角无系统按钮 ②不可拉伸 ③页内确定回传生效 ④页内取消 → payload cancelled;
  - 二级页返回链路:列表 → 新建/编辑/进度/周期 → 取消返回列表、保存返回列表且刷新;托盘直达 → 关窗;
  - 回归:quick-add、提醒四按钮、设置保存(apply_settings 触发)、番茄中菜单变体、`ZENTRAY_UI=qt` 回退对话框形态。
- `npm run build` 重新产出 `web/dist`。

## 改动面汇总

| 层 | 文件 | 改动 |
|---|---|---|
| Python | `zentray/ui/menu_builder.py` | 重写 build_main_menu 条目列表 |
| Python | `zentray/ui/commands.py` | 新增 CurrentTaskCommand;COMMAND_MAP 增删 |
| Python | `zentray/ui/web_host.py` | VueDialog 标志 + 固定尺寸 |
| Python | `zentray/ui/dialog_utils.py` | 新增 apply_dialog_chrome helper |
| Python | 6 个 Qt 对话框文件 | fit_dialog 调用替换为一行式 apply_dialog_chrome |
| Vue | `web/src/views/TaskList.vue` | 新增「周期任务」按钮;跳转携带 from=list |
| Vue | `TaskForm.vue` / `Progress.vue` / `Periodic.vue` | 出口按钮跟随 from 来源 |
| 测试 | `tests/unit/test_menu_builder.py` | 新增 |

## 实施顺序建议

1. 菜单精简(menu_builder + commands + 新单测)——纯 Python,可独立验证;
2. 弹窗窗口层(web_host + dialog_utils + Qt 对话框替换)——纯 Python;
3. Vue 出口行为(TaskList/Form/Progress/Periodic)+ npm build——依赖 1 的周期入口设计,但可并行开发;
4. 全量手动验证清单过一遍。
