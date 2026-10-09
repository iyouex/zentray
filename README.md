# ZenTray 个人禅定看板

> 跨平台（Linux / Windows / macOS）系统托盘 GTD + 番茄钟 + AI 计划/复盘。  
> 当前版本见 `zentray/config.py`（版本规则：[docs/VERSIONING.md](docs/VERSIONING.md)）。

<p align="center">
  <strong>📋 任务轮播 &nbsp;|&nbsp; 🍅 番茄专注 &nbsp;|&nbsp; 🤖 每日计划/复盘 &nbsp;|&nbsp; 📱 多渠道通知</strong>
</p>

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

首次启动可走配置向导（可全部跳过）。程序**无主窗口**，请看**顶栏/托盘**。
安装包未签名/未公证：Windows SmartScreen 选「仍要运行」；macOS Gatekeeper 放行见[用户手册](docs/USER_MANUAL.md)。

### 开发运行

```bash
git clone https://github.com/zen-geek/zentray.git
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

## 功能一览

| 功能 | 说明 |
|------|------|
| **托盘轮播** | 顶栏任务标题轮播；左侧**优先级饼图**（红/黄/绿，按进度填充） |
| **番茄钟** | 专注-短休/长休循环（节奏预设、自动衔接、每日目标、今日统计）；可绑定任务；左：**番茄/休息饼图**（随倒计时填充）；右：倒计时或自定义文案 |
| **任务** | 新建/编辑/进度(10%步进)/完成/废弃；二级分类、截止、提醒（保存时检测与其它弹窗/计划复盘时刻冲突） |
| **周期任务** | 日/周/月模板自动派发 |
| **系统日历** | 设置 → 🖥️ 系统：活跃任务导出 .ics（截止日=全天事件、开启提醒=定时事件），经系统日历应用确认写入 |
| **闪电添加** | `Ctrl+Alt+T` |
| **AI** | **每日计划** + **每日复盘**；多 API 配置（同时启用一个）；毒舌/温柔/干练 + 自定义提示词 |
| **AI 场景能力** | **智能解析**（快速添加/任务表单一句话补全）、**图片识别**（上传或 Ctrl+V 截图转任务草稿）、**任务建议**（优先级/截止/拆分一键应用）；默认关闭，设置 → AI 能力 中开启 |
| **通知** | 固定渠道：应用弹窗、WxPusher（可同时开） |
| **备份** | 设置 → 💾 备份：目录可配、手动备份（AES-256 加密/另存为）、自动周期备份+轮转、从文件恢复（预览计数 + 分类/分区勾选）、历史快照管理 |
| **插件** | 设置 → 🧩 插件：脚本（进度占轮播）与服务（短通知）扩展，支持编辑/删除/使用说明，运行报告可用系统应用（浏览器/md 阅读器）直接打开；任务可关联插件一键运行；≥1 插件时托盘菜单出现「🧩 插件」子菜单，规范见 [docs/plugins/PLUGIN_SPEC.md](docs/plugins/PLUGIN_SPEC.md) |
| **主题** | 浅色 / 深色 / 跟随系统；皮肤 Neo / Aurora / 霓虹 Synth / 黏土 Clay |

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
