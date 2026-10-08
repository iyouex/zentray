# ZenTray macOS 版自动化测试报告（Ubuntu 模拟环境）

> 日期：2026-10-07 · 执行：Claude fork（一次性行）
> 被测对象：`feature/mac-support` @ `67293dd`（worktree `../my_todo-mac`）
> 指令勘误：原始指令含「windows 模拟环境 + 测 macOS 版」的矛盾表述——macOS 版依赖 pyobjc / HIToolbox / .app Bundle，无法在 Windows 模拟层（Wine 等）运行；按用户原意执行「macOS 模拟环境 + 测 macOS 版」。

## 1. GitHub 调研：Ubuntu 上的 macOS 环境

| 仓库 | ★ | 最近推送 | 机制 | 结论 |
|---|---|---|---|---|
| **sickcodes/Docker-OSX** | 52,951 | 2025-11 | OSX-KVM 封装进 Docker，VNC 5999 / SSH 50922 | ✅ **选用**——GitHub 星数第一、安装最简（一条 docker run）、显式面向 CI 自动化 |
| kholia/OSX-KVM | 23,695 | 2026-01 | QEMU/KVM + OpenCore，最贴近底层 | 备选（Docker-OSX 的上游引擎；宿主需自装 qemu） |
| foxlet/macOS-Simple-KVM | 13,940 | 2024-04 | 同上，简化脚本 | ❌ 已停更两年 |
| darlinghq/darling | 13,417 | 2026-09 | Darwin 翻译层（类 Wine） | ❌ 仅支持 CLI/旧 API，**无法运行 PySide6/Qt WebEngine GUI**，对 ZenTray 无效 |

**Docker Hub 现状**：`sickcodes/docker-osx` 仅存 `latest`/`master` 标签——历史版本标签（ventura/monterey/`auto` 无人值守安装）已全部下架。现行 `latest` = OpenCore 引导 + macOS Recovery，**首次安装需经 VNC 人工交互**（磁盘工具抹盘 → 安装 macOS，约 30–60 分钟），此后可 `docker commit` 固化。

## 2. 宿主机（Ubuntu）环境实测

| 项 | 实测 | macOS 虚拟化要求 | 判定 |
|---|---|---|---|
| /dev/kvm | 存在且当前用户可读写（ACL 授权） | 必须 | ✅ |
| CPU 虚拟化 | vmx（VT-x）| 必须 | ✅ |
| AVX2 | 有 | Ventura+ 实际需要 | ✅ |
| 核数 / 内存 | 16 核 / 31 GiB（可用 ~17G） | ≥4 核 / ≥8G | ✅ |
| 磁盘 | 937G 总量，768G 空闲 | 镜像 ~4G + 虚拟盘 64G+ | ✅ |
| Docker | 29.7.1（server 就绪） | — | ✅ |
| 宿主 qemu | 未安装 | OSX-KVM 直跑才需要 | 用 Docker-OSX 规避 |

**结论：本机硬件完全具备运行 macOS 虚拟化条件。**

## 3. 环境安装与启动

| 步骤 | 结果 |
|---|---|
| `docker pull sickcodes/docker-osx:latest` | ✅ 4.28 GiB 镜像入库（保留在宿主 Docker 中） |
| 容器启动（`--device /dev/kvm` + 10022/5900 映射） | ✅ KVM 设备直通成功，entrypoint 正常执行（/dev/kvm 属主改写、ssh host keys 生成） |
| qemu 启动链 | ✅ 到达 InstallMedia 阶段（OpenCore.qcow2 / OVMF 固件 / mac_hdd_ng.img 全部就位，`accel=kvm` 已生效） |
| BaseSystem（Recovery 镜像）获取 | ✅（早期 swcdn 路径受限时绕行，Ventura 经 oscdn.apple.com 完整下载 678MB；详见 3.1 更正） |

### 3.1 BaseSystem 获取：早期「CDN 硬墙」结论已推翻（2026-10-07 晚复核）

镜像内 `fetch-macOS-v2.py` 早期两次尝试（Sequoia/Sonoma，swcdn.apple.com 路径）确实均截断在 1 MiB，当时判定为 IP 级限流硬墙。

**后续实测（Ventura）推翻该结论**：`fetch-macOS-v2.py --shortname ventura` 实际走 **oscdn.apple.com**，678MB 完整下载成功，BaseSystem.img 顺利生成并转入 qcow2。
- 此前阻塞应定性为 **Apple CDN 节点级差异**（同一出口 IP 对 swcdn 部分节点截断在 1 MiB、对 oscdn/osrecovery 节点放行全量），而非 IP 级硬墙；10-07 深夜复核 swcdn 已 404-but-alive、osrecovery 200，节点状态随时漂移；
- fetch 末尾报 `[Errno 25] Inappropriate ioctl for device` 是非 tty 进度条的假报错，可忽略；
- 排障时优先换 `--shortname`（换版本=换 CDN 路径）重试，不必换出口网络。

## 4. Linux 侧可执行的自动化测试（已全部执行 ✅）

在 `feature/mac-support` 检出上，以主仓 venv（Python 3.x）运行：

### 4.1 全量单元测试
```
pytest tests/unit -q  →  339 passed in 9.01s
```

### 4.2 macOS 专项测试（逐条）
```
tests/unit/test_mac_platform.py
  test_mac_tray_module_import_safe_off_darwin   PASSED
  test_mac_hotkey_parse                          PASSED
  test_launchagent_plist_content                 PASSED
  test_hotkey_default_per_platform               PASSED
（4 passed in 0.30s）
```

### 4.3 Linux 导入安全 + 运行时冒烟
- `import zentray.ui.mac_tray` 在 Linux 直接导入 **成功**（平台守卫生效，不影响宿主平台）
- `mac_hotkey_parse('<alt>+<space>')` → `(2048, 49)`（optionKey 修饰位 + Space 键码，正确）

### 4.4 结构审计（自写一次性脚本，AST 级）
对 `zentray/**.py` 全量扫描：`objc/AppKit/Foundation/Quartz/UserNotifications/ServiceManagement` 等 darwin 专属 import **无一条脱离 `sys.platform` 守卫** → `UNGUARDED: NONE ✓`（Linux 导入安全是结构保证，非巧合）

### 4.5 打包工件校验
- `mac_tray.py` / `system_utils.py` / `autostart.py` / `zentray.spec`：`py_compile` 全过
- `scripts/build_mac.sh`：`bash -n` 语法通过
- `pyproject.toml [mac]` extras = pyobjc-framework-Cocoa / UserNotifications / ServiceManagement（≥9.0）✓
- `zentray.spec` 含 `BUNDLE` 且有 darwin 条件守卫（Linux 构建不受影响）✓

## 5. VM 内端到端测试（本轮未达成 · 终局取证 2026-10-08）

**结论先行**：macOS Ventura 安装器在本 VM（qemu 11.1.2 / KVM / q35）中**确定性冻死在
选盘后阶段**，与 VGA 后端、CPU 型号无关（三组配置复现）；且无 shell 通道可绕过
（Terminal 一启动即全屏冻结、现代 macOS 无单用户模式、serial 仅 file 只写）。
VM 内 pytest 本轮不可达——**非网络、非镜像问题**（CDN 旧结论已于 §3.1 推翻）。

**已走通的链路**（全程键盘自动化 HMP sendkey，操作细节与坑见
docs/macos-vm-automated-testing.md 坑13-16）：
- Recovery 引导 → Utilities → 磁盘工具抹盘（10-07 完成；/image 64GiB qcow2 虚拟容量正常）
- 安装器：Utilities→安装 tile（tab+spc）→ 欢迎（ret=Continue）→ 选盘面板
  （tab,tab,spc 前进）——到达选盘后 ~45-66s WindowServer 全屏冻结（menubar 时钟停走）

**冻结矩阵**（同盘同 BaseSystem，仅换 qemu 参数，均以 menubar 时钟 md5 跨分钟采样判定）：

| 配置 | 冻结点 | 证据 |
|---|---|---|
| `-vga vmware -cpu host` | 许可面板永久 busy；Terminal 启动即冻 | spinner 静止；整屏像素扫描无任何按钮 |
| `-vga std -cpu host` | 选盘后 ~45s | 3 帧跨 4 分钟 md5 全等 `a2397521` |
| `-vga std -cpu Haswell-noTSX-IBRS` | 选盘后 ~66s | walk4 冻结检测器 `disk_alive FROZEN` |

**排除项**：网络路径（容器→Apple CDN curl 通、qemu 持有 APNs ESTABLISHED 连接、
冻结时安装器零 443 请求 = 非网络等待）；目标盘（qemu-img 64GiB 正常）；输入通道
（sendkey 重试封装可靠送达，含容器 /dev/tcp 间歇 ENOENT 窗口）；BaseSystem 完整性
（oscdn 678MB 实测下载，§3.1）。

**遗留环境**：容器 `osx-autotest` 保留运行（qemu=std+Haswell 配置、VM 冻结态取证）；
4444 monitor 仍发布 0.0.0.0（坑9，仅容器销毁可清）；payload server `/home/arch/payload`
（go2.sh / vm_setup.sh / zentray-mac.tar.gz 均未被消费，VM 内无 shell 可拉取）。

**后续路线**（原「换网络重跑」手册已过时——网络不是阻塞）：
1. 真 darwin CI 首选 GitHub Actions `macos-latest`（不变，见 §6 建议 1）
2. 本机 VM 续试方向：换 qemu 版本（8.x 系）/独立大内存宿主/官方 docker-osx 镜像自带
   Ventura 参数集——本文三组参数已证伪，勿再重复
3. Mac 真机人工验收 `feature/mac-support`（NSStatusItem 渲染、UN 授权、SMAppService）

## 6. 结论与建议

| 目标 | 状态 |
|---|---|
| GitHub 调研最佳 Ubuntu macOS 环境 | ✅ Docker-OSX（52.9k★），Darling/Simple-KVM 有据否决 |
| 安装环境 | ✅ 镜像入库 + 容器/KVM/qemu 启动链全部验证通过 |
| VM 内自动化测试 | ⛔ 安装器在选盘后阶段确定性冻结（三组 qemu 参数复现，VGA/CPU 均排除），无 shell 通道绕过；VM 内 pytest 本轮不可达，取证见 §5 |
| Linux 侧全量自动化验证 | ✅ **339 单测全过 + mac 专项 4/4 + 导入安全冒烟 + AST 结构审计 + 打包工件校验**（§4） |

**建议**：
1. **真 darwin CI 首选 GitHub Actions `macos-latest` runner**——公开仓库免费、真实 Aqua 会话、无 CDN/虚拟化冻结问题；把 darwin 测试序列（pytest tests/unit + mac_tray 导入 + NSStatusItem 冒烟）写成 workflow 即可覆盖 mac 分支回归，这是本 VM 路线证伪后的唯一自动化出路
2. 本机 VM 暂降级为「已证伪环境」存档（容器/取证保留，续试方向见 §5 后续路线，勿按旧网络手册重跑）
3. `feature/mac-support` 的 darwin 专属路径（NSStatusItem 实际渲染、UN 通知授权、SMAppService 注册）仍需一次真机/GH Actions 验收方可放行发版
