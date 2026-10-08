# ZenTray 回头看：复盘与再设计（2026-10-08，基线 v0.7.3）

> 范围：全程序架构复盘。证据来自代码现状 + 自 2026-06 以来的 churn 统计 + v0.7.3 三平台发版过程。
> 结论先行：**架构底盘是好的，不需要重写**；真正的债集中在五处，其中最大的一笔（双 UI 分叉）已经实质违约，建议删而不是修。

## 0. 现状快照

| 维度 | 数字 |
|---|---|
| 后端 Python | 155 文件 / 16.4k 行（最大 handlers.py 1635） |
| 前端 Vue | 10.6k 行（最大 Settings.vue 3065） |
| 测试 | 350 单测，Linux 容器 / macOS CI / Windows 真机三平台全绿（48s 跑完） |
| 平台层 | Linux(AppIndicator 桥) / macOS(NSStatusItem) / Windows(任务栏中央) 三后端 + Qt 兜底 |
| 数据 | 单文件 JSON（RLock 按路径加锁 + tmp 原子写 + 备份轮换） |
| 发版 | staging→master 三层流，双平台 CI 自动挂资产，v0.7.3 全链路走通 |

## 1. 老化得好的部分（不要动）

- **托盘平台工厂**（`tray.py::create_tray_backend` + `TrayImplementation` ABC）：mac/win 两分支平行开发数月，合入 staging 时冲突只有 3 处 union——按平台分派、共享 controller/renderer/menu_builder 的设计完全兑现。这是本次复盘最值得保留的资产。
- **插件子系统**（manifest/loader/runtime/triggers 独立成包，入口平台分派）：300+ 行的子系统与主业务零耦合，用户目录插件 + 内置插件双源。边界干净。
- **文件 IO**：`file_io.py` 按路径 RLock + 原子替换 + 自愈，515 行 data_migration 有版本化迁移链。单用户数据量级下不需要数据库。
- **测试布局**：test 文件与源文件一一对应，churn 热点（menu_builder ↔ test_menu_builder）同步演化。
- **Worker 模型统一为 QThread**：watcher/nightly/reminder/plugin_trigger 四个 worker 同构，启停都挂在 `apply_settings` 重评估上。

## 2. 债务清单（按疼痛排序，每项给证据 + 再设计 + 工作量）

### D1 双 UI 分叉已经实质违约 —— Qt 回退 UI 应当删除

**证据**：`settings_dialog.py`（958 行）中 `skin` 出现 0 次、`report_rotation`/`tray_icon_countdown` 0 次——Vue Settings.vue 同期改了 30 次，Qt 设置对话框一个都没跟上。设置项漂移不是风险，是既成事实。

**根因**：`web/dist` 随仓库提交（.gitignore 里明确注释），所以**任何源码运行和任何发行包里 Vue 永远可用**，`try_vue_*` 永远命中。Qt 回退（settings_dialog 958 + dialogs 646 + task_list_dialog ~250 + setup_wizard 375 + reminder_dialog ~150 + overlay ~200 ≈ **2500 行**）只在手工删除 web/dist 后才可达——即不可达。

**再设计**：删除全部 Qt 回退 UI（`try_vue_*` 变成直接调用，`vue_ui_available()` 为假时打日志并提示 `npm run build`）。`dialog_utils.py` 保留——它的窗口 chrome 被 `web_host.py` 的 Vue 窗口复用，是活代码。`setup_wizard.should_show_wizard` 判断逻辑保留，Qt 向导壳删。
**工作量**：删 6 文件 + commands/main 里 6 处分支拉直 + 清对应测试，净 **-2400 行左右**。
**注意**：这是功能删除，需用户确认后再动。

### D2 handlers.py 单体 + 237 行 if 链路由

**证据**：1635 行、50+ 自由函数、churn 榜第二（28 次）。每个新 API 都要往 `handle_request` 的 if 链里插行，前后端联调时该文件几乎必改。

**再设计**（不换框架， stdlib 内解决）：
1. 把 if 链改成**路由表 dict**：`ROUTES: dict[tuple[str, str], Handler]`，前缀路由（`/api/tasks/`）单列一张前缀表。`handle_request` 缩到 ~30 行。
2. 按资源拆三个模块：`api/tasks.py` / `api/plugins.py` / `api/system.py`，`handlers.py` 只留 ApiContext + 路由装配。
**工作量**：一次机械搬迁 + 测试全绿验证，半天。**收益**：新端点不再碰核心文件，review diff 独立。

### D3 main.py 装配巨函数 + getattr 服务定位

**证据**：509 行里 `main()` 一个函数 ~270 行；`getattr(runtime.controller, "plugin_runtime", None)` 式挖属性 7 处；`_ApiUiRelay` 内联类 60 行定义在函数体内（缩进 4 层）；`apply_settings` 被 monkeypatch 包装（`runtime.controller.apply_settings = apply_settings_with_workers`）。

**再设计**：
- TrayController 事实上已是服务容器（持有 plugin_runtime/plugin_loader/pomodoro_service/report_rotation），把它**合法化**：这些属性在 `dependencies.py::init_tray_controller` 里显式赋值，main.py 不再 getattr。
- `_ApiUiRelay` 挪到 `api/handlers.py` 旁或 `ui/` 独立文件。
- `apply_settings` 的 worker 重启钩子改成 TrayController 自带槽（controller 已有 `apply_settings`，加一行 emit 或在依赖装配处 connect）。
**工作量**：搬迁为主，~1 天。**收益**：main.py 回到 ~150 行纯装配，monkeypatch 消失。

### D4 TaskService 无锁跨线程 —— 唯一的真实风险项

**证据**：`TaskService` 零锁（`grep Lock task_service.py` = 0），却被三种线程并发调用：HTTP 线程（Vue API，ThreadingHTTPServer）、4 个 QThread worker、Qt 主线程。文件层 RLock 保住了落盘不坏，但服务层的读-改-写（如 update_task 前的 find_task）存在丢更新窗口。至今未爆只因单用户低频写。

**再设计**：`TaskService` 加一把 `threading.RLock`，公共写方法（create/update/mark_done/abandon/select/update_task_reminder）进临界区。文件锁在更底层，不会死锁；临界区短，无性能问题。
`# ponytail: 单把服务锁，按任务粒度锁需先证明丢更新真的发生在生产`
**工作量**：半天（含一个并发压测单测：N 线程并发 mark_done 不丢事件）。

### D5 API server 无鉴权 + `Access-Control-Allow-Origin: *`

**证据**：`server.py` 绑 127.0.0.1 随机端口，但 `_cors()` 对所有响应发 `ACAO: *`，不校验 Origin/Host。任意本地进程可打全 API；恶意网页可借 DNS rebinding 读任务数据。单用户桌面威胁模型下风险低，但修复只要十行。

**再设计**：`_dispatch` 入口校验 `Host` 头必须是 `127.0.0.1:<port>`/`localhost:<port>`，非 `/api/` 前缀请求带 `Origin` 头时校验同源。CORS 收成同源。
**工作量**：10 行 + 2 个单测。

### 小项（顺手清）

- **renderer.py 43 行纯转发**：`TrayRenderer` 每个方法一行直呼 backend，零逻辑（`hasattr set_state` 分支是死的——所有 backend 继承 ABC 已有 `set_state`）。删类，controller 直呼 backend。
- **core/ vs repositories/ 目录分裂**：`core/repository.py` 放 ABC、`repositories/` 放实现，两目录六文件互相 import。合并进一处，下次顺手做，不单开任务。
- **web/dist 每次重建产生提交噪音**（churn 榜第一 62 次全是 index.html hash 变化）：保留现状（无 Node 环境直接打包是发版链路依赖），但 feature 分支开发期可只在合入 staging 前重建一次，减少 merge 冲突面。

## 3. 再设计路线图

| 档 | 内容 | 净行数变化 |
|---|---|---|
| **立即**（纯删/小修，一个 staging 周期） | D5 鉴权 10 行、D4 服务锁、renderer 删除 | +80 / -45 |
| **下个 MINOR**（v0.8.0 候选主题：「瘦身」） | D1 删 Qt 回退 UI、D2 handlers 拆分 | -2400 / 拆 3 文件 |
| **随 D2 顺带** | D3 main 装配整理 | main.py 509→~150 |
| **明确不做**（YAGNI） | 换 HTTP 框架；JSON→SQLite 迁移；插件市场；多设备同步；Qt 回退 UI「补齐」到与 Vue 平齐 | — |

**判级依据**：D4/D5 按现规则是 PATCH（修复）；D1/D2/D3 合计删/移 3000+ 行，属里程碑级瘦身，配 v0.8.0 的 MINOR。

## 4. 一句话总结

底盘（平台工厂、插件、文件层、测试）不动；把「Vue 永远可用所以 Qt 回退永远不可达」这层窗户纸捅破，删掉 2500 行已烂掉的分叉 UI；给唯一真实的并发窗口上一把锁；路由表替换 if 链——ZenTray 就是一个 12k 行而不是 16k 行、三平台全绿、无已知竞态的程序。
