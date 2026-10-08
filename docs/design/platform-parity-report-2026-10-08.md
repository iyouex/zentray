# Windows / macOS 功能对齐 Linux 检查报告（2026-10-08）

基线：staging `f35de34`（含 ui-skins 四皮肤）。
检查方法：Windows VM 实测 24 失败逐一归因（`docs/windows-test-report-2026-10-07.md` §4 + `/home/iyoukai/zentray-win-vm/incoming/` 证据）+ macOS 静态代码审查（osx-autotest 容器被占用，未动）。

## 1. 平台能力对齐矩阵

| 能力 | Linux（基线） | Windows | macOS |
|------|--------------|---------|-------|
| 托盘后端 | AppIndicator/QtStandard（`tray.py` 工厂） | QtStandard 派生：动态 QPainter 图标 + tooltip 全量 + 左键速览面板 + 任务栏中央按钮（1×1 离屏窗口） | 原生 NSStatusItem（icon+标题轮播+NSMenu）`mac_tray.py` 334 行 |
| set_state / update_menu / show_notification / shutdown | ✅ TrayImplementation | ✅（菜单/通知继承 QtStandard；win_tray 本体补 set_state/shutdown） | ✅ 全覆盖，通知带 on_click 回调 + notification_clicked 信号（强于基线） |
| 全局热键 | pynput（跨平台同源） | 同 Linux，无需改动 | pynput + Accessibility 权限探测（system_utils +136 行） |
| 开机自启 | `.desktop` | HKCU Run（winreg） | SMAppService + launchctl 回退（autostart +105 行） |
| 平台入口分派 | `create_tray_backend` 工厂 | ✅ win32 分支 | ✅ darwin 分支 |
| 打包 | Linux 打包既有 | 沿用（tar 实测暴露缺 bundled_plugins，见 §2-B） | .app（LSUIElement）+ build_mac.sh + zentray.spec 分支 |
| CI | — | VM 手动回归（zt-win-test 容器） | GitHub Actions workflow_dispatch（test-macos.yml） |
| 平台单测 | 共享 349 项 | test_win_tray.py（128 行） | test_mac_platform.py（67 行） |

**结论：托盘/热键/自启/打包四层平台实现齐备，业务与前端保持平台无关（`tray.py` 工厂收敛差异），符合 2026-10-01 跨平台约定。**

## 2. Windows VM 24 失败归因与处置

| 类 | 数量 | 根因 | 定性 | 处置 |
|----|------|------|------|------|
| A | 14 | 插件 `.sh` entry 直接 Popen → WinError 193 | **代码缺陷** | ✅ `_entry_command` 平台分派（.py→sys.executable / .sh→bash，缺 bash 给可操作文案） |
| B/C | 6 | VM 交付 tar 包缺 `bundled_plugins/`（tar tzf 实证） | **环境打包遗漏，非代码** | ⏳ 重打 tar 后 VM 复跑即绿 |
| D | 1 | 饼图图标依赖 Pillow 但 pyproject 未声明 | **依赖声明缺陷** | ✅ `Pillow>=10.0.0` 入 dependencies |
| E | 1 | 报告路径正则不认反斜杠（Windows 路径） | **代码缺陷** | ✅ `[\w./\\~-]+\.html` |
| F | 1 | 测试 `.read_text()` 缺 encoding（cp1252 撞中文归档） | 测试缺陷 | ✅ `encoding="utf-8"` |
| G | 1 | 测试硬编码 `/etc` | 测试缺陷 | ✅ `WINDIR` 回退 |

回归测试：`test_entry_command_platform_dispatch`（.py/.sh/其他三路分派 + 缺 bash 报错）。

## 3. 落地与验证

- **feature/win-taskbar-center**（worktree `../my_todo-win-center`）：rebase 到 `f35de34`（皮肤白名单 ∪ 任务栏字段，Settings.vue/settings_manager.py 冲突取并集；web/dist 以 npm 重建，含四皮肤）
  - `f905bef` 托盘后端 → `91248e4` 速览面板 → `23b7b36` 任务栏中央按钮（含重建 dist）→ `1a8be40` 本轮 6 项修复
- **feature/mac-support**（worktree `../my_todo-mac`）：干净 rebase 到 `f35de34`，无冲突，无改动需求
- 单测（docker `zentray-test:3.12`，xvfb）：win-center **309 passed** / mac **312 passed**（基线 staging 307；排除 5 个 GUI-paint 模块——QPixmap 在本容器内核必 core dump，与环境无关，模块未受本轮改动影响，VM/宿主覆盖）

## 4. 残留风险与建议

1. **VM 复跑 ✅（2026-10-08）**：重打包（含 `bundled_plugins/`）经 `zt-win-test` 真机复跑 —— **collected 350 items，350 passed in 48.63s，exit=0**（350 = 基线 349 + 新增回归 `test_entry_command_platform_dispatch`；rootdir `C:\`，Win10 LTSC 19044 / Python 3.12.10 / pytest 9.1.1）。24 项失败全部转绿，B/C 根因（tar 缺 bundled_plugins）实证消除。
   - 注：本轮 guest→宿主 HTTP 出口中途单向死亡、且 `docker stop` 非正常关机致 `%USERPROFILE%` 下小文件未落盘（离线 pytsk3/7z 双读均不可得），结果以多屏互证的宿主侧截图记录为准（collected/汇总行/DONE.txt exit=0 三证一致）；`C:\` 根的全新解包（zentray/tests/pyproject）已离线核实。后续复跑建议：批处理开头先 curl 探活接收器，关机用 guest 内 `shutdown /s` 而非 `docker stop`。
   - 通道教训（已实测）：VNC `vncdotool type` 的 shift 字符（`:` `&`）在 QEMU VNC 层稳定丢失且连发约 20 键后输入整体卡死（需重启 VM）；QEMU HMP monitor `sendkey`（`telnet localhost:7100`）逐键注入稳定可用，但无 `backslash` 键名——UNC/盘符命令打不进去。终极通道：HMP 热插 ISO U 盘（`drive_add`+`device_add usb-storage`）+ 无反斜杠两行命令（`E:` → `run-v6.bat`）跑通全程。
2. Windows 跑 `.sh` 插件需 bash（Git Bash 入 PATH）；缺失时报可操作中文文案而非系统错误。
3. macOS 仅静态审查 + 单测；osx-autotest 空闲后建议按 `docs/macos-vm-automated-testing.md` 补一轮真机验证。
4. 平台分支均未合回 staging——按约定由用户决定合入时序，合入前两分支需再 rebase。
