# ZenTray 个人禅定看板

> 跨平台（Linux / Windows / macOS）系统托盘 GTD + 番茄钟 + AI 计划/复盘。  
> 当前版本见 `zentray/config.py`（版本规则：[docs/VERSIONING.md](docs/VERSIONING.md)）。

![任务列表](docs/images/task-list.png)

**无主窗口**：常驻顶栏/托盘，右键图标打开全部功能；Windows 左键托盘呼出速览面板。

<p align="center"><strong>📋 任务轮播 &nbsp;|&nbsp; 🍅 番茄专注 &nbsp;|&nbsp; 🤖 每日计划/复盘 &nbsp;|&nbsp; 📱 多渠道通知</strong></p>

> 📖 **用户手册**：[docs/USER_MANUAL.md](docs/USER_MANUAL.md)  
> 🖥️ **Vue 前端**：[docs/FRONTEND_VUE.md](docs/FRONTEND_VUE.md)

---

## 快速开始

### 安装包

| 平台 | 包 | 方式 |
|------|-----|------|
| Ubuntu / Debian | `zentray_*_amd64.deb` | `sudo apt install ./zentray_*.deb` → 命令 `zentray` |
| Windows (x64) | `zentray_*_windows_x64.zip` | 免安装，解压后运行 `ZenTray/ZenTray.exe` |
| macOS (arm64) | `zentray_*_macos_arm64.zip` | 解压 `ZenTray.app` 拖入「应用程序」 |

首次启动可走配置向导（可全部跳过）。安装包未签名/未公证：Windows SmartScreen 选「仍要运行」；macOS Gatekeeper 放行见[用户手册](docs/USER_MANUAL.md)。

### 开发运行

```bash
git clone https://github.com/iyouex/zentray.git
cd zentray
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
# 前端（对话框为 Vue + Arco，需先构建）
cd web && npm install && npm run build && cd ..
python -m zentray.main
```

强制使用原生 Qt 对话框：`export ZENTRAY_UI=qt`

### 可选环境变量（`.env` 或数据目录）

```env
WXPUSHER_APP_TOKEN=...
WXPUSHER_UID=...
AI_API_KEY=...
AI_API_BASE_URL=https://api.openai.com/v1
AI_MODEL_NAME=gpt-4o
```

也可用托盘 **设置** 配置（推荐）。

---

## 界面速览

**速览面板**（Windows 左键托盘）——轮播槽任务卡（优先级/截止/子任务进度）+ 番茄钟状态，◀▶ 沿活跃序换位：

![速览面板](docs/images/glance.png)

**新建任务** —— 一次性/周期模式；分类、优先级、**统一时间组件**（一次性：▶开始/⏰截止/●弹窗 笔刷 + 月历 + 24h 可拖时间轴，新建默认今天起/次日止；周期模板：行式必选起止 + 周期内弹窗点位，派发实例后才有图形件；跳过公休日联动置灰，时分默认取分类提醒时间窗）、子任务、附件/链接、关联插件：

![新建任务](docs/images/task-form.png)

**闪电添加** —— 全局热键 `Ctrl+Alt+T` 呼出，一句话记待办，回车入库：

![闪电添加](docs/images/quick-add.png)

**设置** —— 左侧导航分三组：**日常工作**（任务 / 番茄钟）、**集成与通知**（AI 能力 / 通知 / 插件）、**应用与数据**（系统 / 备份 / 历史）；即时生效项带「即时」标记，其余随保存写入：

![设置](docs/images/settings.png)

**插件面板**（托盘「🧩 插件」）—— 分类筛选 + 逐插件卡片，脚本与服务一键运行/启停：

![插件面板](docs/images/plugins-panel.png)

### 核心能力

| 能力 | 说明 |
|------|------|
| **托盘轮播** | 顶栏任务标题轮播；左侧优先级饼图（红/黄/绿，按子任务进度填充） |
| **番茄钟** | 专注-短休/长休循环；节奏预设（经典/深度/超长）、每日目标、今日统计；可绑定任务 |
| **AI** | **每日计划 + 每日复盘**（插件「朝闻/暮省」，随关联周期任务调度）；多 API 配置同时启用一个 |
| **AI 场景能力** | **智能解析**（一句话补全任务）、**图片识别**（截图转任务草稿）、**任务建议**（一键应用）；默认关闭，设置 → ✨ AI 能力 中开启 |
| **通知** | 应用弹窗、WxPusher、飞书机器人（可同时开）；插件通知按**插件级**选渠道，格式模板可自定义 |
| **系统日历** | 订阅源自动同步：任务增删改自动重写 .ics 源文件，日历应用订阅即保持同步（Linux/macOS）；周期模板可投影未来日程 |
| **飞书同步** | 任务单向推送飞书「ZenTray」日历与任务清单（自建应用授权，完成/删除自动撤下）；配置见 [docs/FEISHU_SYNC.md](docs/FEISHU_SYNC.md) |
| **备份** | AES-256 加密、自动周期备份+轮转、从文件恢复（预览 + 分类勾选） |
| **插件** | 脚本与服务扩展，参数预设、插件级通知；插件随所关联任务的弹窗时刻自动运行，规范见 [docs/plugins/PLUGIN_SPEC.md](docs/plugins/PLUGIN_SPEC.md) |

---

## 架构（简图）

```
托盘 (AppIndicator / Qt)
  ├── 轮播 / 番茄图标与文字
  └── 菜单 → Vue 对话框 (QWebEngineView)
                 └── 本机 HTTP API → TaskService / SettingsManager
后台：Watcher / Reminder / AI 调度 Worker
```

业务逻辑在 **Python**；设置与业务弹窗优先 **Vue 3 + Arco Design**（无 `web/dist` 时回退 Qt）。

---

## 打包

```bash
cd web && npm ci && npm run build && cd ..
./scripts/build_package.sh
# 产物: dist/releases/zentray_*_amd64.deb
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | 分环境安装与使用 |
| [docs/FRONTEND_VUE.md](docs/FRONTEND_VUE.md) | 前端开发与路由 |
| [docs/VERSIONING.md](docs/VERSIONING.md) | 版本号规则 |
| [LICENSE](LICENSE) | MIT |

---

## 许可证

MIT
