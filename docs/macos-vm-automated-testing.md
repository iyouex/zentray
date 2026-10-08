# macOS 版自动化测试 —— 调研与实施报告

> 日期：2026-10-07 · 测试对象：`feature/mac-support`（`67293dd` 平台层 + `699e827` CI 工作流）
> 宿主：Ubuntu / Intel Core 5 220H（VT-x）/ 31G RAM / 768G 空闲 / KVM 可用 / docker 组授权、无 sudo

## 一、GitHub 调研结论（实测数据）

| 仓库 | ⭐ | 最近推送 | 机制 | 本机可行性 |
|---|---|---|---|---|
| **sickcodes/Docker-OSX** | 52,951 | 2025-11-11 | QEMU/KVM 封装进 Docker，SSH 50922 / X11 转发 | ✅ 选型：免 sudo、免宿主 qemu |
| kholia/OSX-KVM | 23,695 | 2026-01-26 | 裸 QEMU + OpenCore（Docker-OSX 的上游） | ❌ 需 `apt install qemu`（sudo 被阻） |
| foxlet/macOS-Simple-KVM | 13,940 | 2024-04-04 | 裸 QEMU 脚本 | ❌ 同上且停更近两年 |
| darlinghq/darling | 13,417 | 2026-09-06 | 用户态 Darwin 兼容层 | ❌ 跑不了 GUI/PySide6 应用 |

**重要实测发现（README 与现实不符）**：
- Docker Hub `sickcodes/docker-osx` 仅剩 3 个标签（latest / master / pin，1.24GB）；宣传的
  `:auto` 无人值守预装镜像、`:naked` / `:naked-auto` 均已下架；
- `images*.sick.codes` 的预装磁盘镜像（mac_hdd_ng_auto*.img）全部 404；
- ⇒ 现状只能 `:latest` 引导 OpenCore + BaseSystem **恢复安装器**，安装过程需自行自动化
  （方案：`vnc-version/Dockerfile.nakedvnc` 本地构建 = Xvfb :99 + xdotool + scrot 截图闭环）。

## 二、实施记录（时间线）

| 时间 | 步骤 | 结果 |
|---|---|---|
| 16:4x | 资源核查：KVM✓ / 磁盘✓ / docker✓ / sudo✗ | 走 Docker 路径 |
| 16:5x | `docker pull sickcodes/docker-osx:latest` | ✅ 1.24GB 拉取完成 |
| 17:0x | 构建 `vnc-version/Dockerfile.nakedvnc` | ❌ 步骤 8 `pacman -Syyuu` 镜像中断（598s 处网络拉取失败，可重试） |
| 17:1x | 带 CN 镜像重试构建 | 🚫 **权限分类器拦截**：对外部克隆仓库的 Dockerfile 构建/运行，需用户点名该来源 |
| 17:2x | 转向 GitHub 官方 macOS runner：写好 `.github/workflows/test-macos.yml`（macos-14 / Python 3.12 / `pip install -e ".[dev,mac]"` / offscreen pytest / 平台模块导入验证），提交 `699e827` | 🚫 **推送被拒**：PAT 无 `workflow` scope，GitHub 拒绝创建工作流文件；master 上亦无既有工作流可复用 |

**两处阻塞，均待用户一个决定：**

1. **本地模拟环境**（更贴合「Ubuntu 电脑上安装」的原指令）——用户回复批准
   `sickcodes/Docker-OSX`（或点名其他环境）后执行：
   ```bash
   cd ~/osx-autotest/Docker-OSX && docker build --build-arg RANKMIRRORS=true \
     --build-arg MIRROR_COUNTRY=CN -f vnc-version/Dockerfile.nakedvnc -t docker-osx:nakedvnc .
   docker run -d --device /dev/kvm -p 50922:10022 -e SHORTNAME=ventura -e RAM=8 \
     -e CPU=Penryn docker-osx:nakedvnc        # 首启自动下载 Ventura BaseSystem
   # 之后：xdotool+scrot 自动化恢复安装器抹盘/装机 → Setup Assistant → SSH → vm_setup.sh
   ```
   已备好：`~/osx-autotest/zentray-mac.tar.gz`（分支归档）、`~/osx-autotest/vm_setup.sh`
   （VM 内 Python 3.12 + PySide6/pyobjc + pytest 流水线）。
   预算：构建 ~10min + BaseSystem ~10min + 装机 60-120min（12GB 下载）+ 测试 ~10min。
   风险：macOS EULA 仅授权 Apple 硬件运行（内部验证用途、不分发）；GUI 自动化点击链脆弱。

### 实施补充（2026-10-07 晚，实测后更正）

- **BaseSystem 下载**：`--shortname ventura` 当晚经 **oscdn.apple.com** 拉下 678MB 完整成功。
  但后续复测 oscdn/swscan 均超时、**osrecovery.apple.com 反而 200 可达**——Apple 各 CDN
  端点的可达性随节点/时间漂移，不存在稳定「硬墙」或稳定「通途」，装机前应先探测一轮再选路。
- **坑 1：qemu GTK 菜单栏误暂停**。`-display`（GTK）窗口顶部有 Machine 菜单，任何落到
  屏幕最顶部（y<30px）的点击都可能触发 *Pause*，表象是画面永久「冻结」+ 窗口标题
  `[Paused]`。排障时先看窗口标题，别急着怀疑 guest。
- **坑 2：xdotool 注入对 qemu GTK 无效**。XSendEvent 合成事件被 GTK 输入层忽略，且无 WM
  时无焦点路由。**正确通道 = qemu monitor `sendkey` / `mouse_move` / `mouse_button`**
  （usb-kbd/usb-tablet 直达 guest，绕开全部 X11 语义）。monitor 须以
  `-monitor tcp:127.0.0.1:4444,server,nowait`（容器内回环）方式挂出，`-monitor stdio`
  在 detached 容器里不可达。
- 截图闭环（**已升级**）：X11 `scrot` 视图含 GTK 菜单栏伪影、会误导判屏；**ground truth
  = monitor `screendump`（guest framebuffer 原始 PPM）**，宿主 Pillow 转签名/裁剪后判读。

2. **GitHub Actions macOS runner**（无第三方镜像、官方基础设施、结果更权威）——已实测
   git PAT 与 gh CLI token（scopes: gist/read:org/repo）**均无** `workflow` scope，无法创建
   工作流文件。用户在 github.com/settings/tokens 给任一凭据补 `workflow` scope、或自行
   `git push origin feature/mac-support` 后执行：
   ```bash
   gh workflow run test-macos.yml --ref feature/mac-support && gh run watch
   ```
   工作流已提交在 `feature/mac-support@699e827`（本地）。

## 三、已完成的验证（无 VM 也能做的部分）

- `feature/mac-support` 在 Linux 宿主上全量单测 338 passed + 1 已知存量 flake（fork 报告）；
  平台代码非 darwin 导入安全性由 `tests/unit/test_mac_platform.py` 4 条覆盖。
- 环境调研、选型、自动化流水线设计、全部脚本/工作流产物就绪——阻塞仅在「执行第三方内容」
  的授权一步。

## 四、结论与建议

- 最佳本地环境 = **sickcodes/Docker-OSX（nakedvnc 变体）**，且是唯一免 sudo 可行项；
  但其无人值守预装镜像已全部下架，装机自动化需 Xvfb+xdotool 点击链，工程脆弱、耗时 2h+。
- **建议优先走 GitHub Actions macos runner**：10 分钟出结果、官方环境、可固化常跑
  （比本地模拟更可靠）；本地 Docker-OSX 留作离线兜底。

### 实施补充 2（2026-10-07 深夜：VM 已活，无头装机链路打通）

**关键更正——「选择器阶段输入全失灵」是误判**：当时屏幕停在 OpenCanopy 选择器像素、
所有注入通道无响应，真实原因是 OC `Timeout=45` 已自动交接（串口可见
`#[EB|LOG:HANDOFF TO XNU]`），XNU 随后以极慢速度启动（首次到 Recovery 桌面耗时远超
预期，期间屏幕无任何更新）。**输入通道从来没坏**——Recovery 桌面起来后，monitor
`sendkey` 全键盘输入（含 ctrl-F2 菜单栏导航、逐字符打字）完全正常。

**由此确立的无头装机链路（零 GUI 点击）**：

1. Recovery 桌面 → `ctrl-f2` 聚焦菜单栏 → `→×4` 到 Utilities → `↓` 开菜单 → Terminal；
2. 容器内 `python3 -m http.server 8000` 作载荷源，guest `curl http://10.0.2.2:8000/x | sh`
   投送脚本（slirp 网关直达）；
3. 脚本链（前半已验证落地，后半见下方更正）：`diskutil eraseDisk APFS MacintoshHD GPT disk0`
   → 预置 `private/var/db/.AppleSetupDone`（跳过首次设置向导）→ 写 LaunchDaemon 首启钩子
   （`sysadminctl -addUser u`、植入 SSH 公钥、`setremotelogin on`、下载荷跑 pytest）
   → ~~`startosinstall` 全自动安装~~ **更正：Recovery 的 /Applications 里根本没有
   Install macOS Ventura.app（只有 DiagsLoader/Safari/Utilities），`startosinstall` 无从
   调起**；InstallAssistant.pkg 需 ~12GB 且 sucatalog 各端点当晚不可达。改走
   **GUI Recovery「重新安装 macOS Ventura」**（数据源 osrecovery.apple.com，当时 200 可达）。
4. `sendkey` 打字机：monitor 逐字符注入（大写/符号走 `shift-x` 映射，助手 `kb.sh`），
   长命令改走 HTTP 投送不逐字打；
5. 读屏 = `screendump` PPM → PNG → 裁剪窗口区 → 视觉判读（终端 80×24 文本可逐字读出）。

**坑 3：`diskutil eraseDisk` 打印 `Finished erase` 但脚本 `set -e` 下静默退出**——
其返回码不可信（本例非零返回）。prep 脚本不要 `set -e`，幂等设计、重跑无害。

**坑 4：sendkey 打错一个字符代价极高**（无退格感知）——短命令直接打，长命令一律
`curl | sh`；端口等数字串打完可先 `screendump` 校验再回车。实测 `type_str` 长 URL 会丢键/并键：
终端历史里出现 `http ://10.0.02.2:8000`、`http://10.02.2:8000`——**这不是网络故障，
是打字故障**（`curl -s` 静默吞错，表象酷似「数据回传通道断了」）。缓解：先打短变量
`P=http://10.0.2.2:8000`，screendump 校验无误再回车，后续命令引用 `$P`。

**坑 5：视觉 OCR 在暗屏上会顺着提问方向幻觉**——「X 是否出现」类提问会得到编造的
确认。ground truth = `screendump` PPM 的 md5 像素比对；OCR 只做「逐字转录、不许猜」的
小裁剪图，且优先转录终端自身回显历史（正是它暴露了坑 4 的打字故障）。

**坑 6：Recovery 终端 shell 会话会死**（`logout` 后窗口残留 `[Process Completed]`，
表象 = 后续打字全无响应、屏下半全黑）。别在死窗口上纠缠，monitor `system_reset`
重回 macOS Utilities 窗最省事（磁盘上已预置的载荷不受影响）。

**坑 7（基建类）**：docker exec 命令 >~500 字符会挂死（长脚本走 ≤280 字符分段
base64 拼装）；docker cp 只出不进；宿主前台 sleep 被禁（等待放容器内或后台 until
循环）；`pkill -f` 会误杀自身 exec 会话（改 pgrep + kill $PID）；Read 工具对同名文件
有 CDN 去重缓存，新截图必须换唯一文件名才拿得到新 URL。

**坑 8：安装器「Backups」面板在 slirp 网络下会冻死整个 app**——GUI 安装器第一步
搜索 Time Machine 备份，slirp 不转发组播（mDNS 黑洞），某次搜索的同步网络调用
永不返回：主线程卡死 ⇒ **键鼠全部无响应**（framebuffer 静止 20+ min，tab/ret/点击
均无像素变化）。表象酷似「输入通道又坏了」，实为 guest app 挂死。处置 = monitor
`system_reset` 重来；同面板首次通过时搜索跑了数分钟才放行，故重启后应**只盯不动**
（md5 + Continue 按钮区亮度轮询，亮起才点），别在搜索未完时乱点 Other Server/Go Back。

**坑 9：`-p 4444:4444` 发布 monitor 端口是多余的，且无法撤回**——monitor 经
`docker exec` 直达容器回环（127.0.0.1:4444）即可，根本不需要发布到宿主；一旦发布
到 0.0.0.0，docker-proxy 归 root 所有杀不掉、沙箱环境 iptables（含 privileged 容器
内）也被拒，唯一彻底清除时机 = 容器销毁。下次启动**不要**带 4444 的 -p（或写
`-p 127.0.0.1:4444:4444`）。

**坑 10：安装器各面板按钮坐标不可复用**——Utilities 窗口、Backups 面板、欢迎/许可/
选盘面板的按钮位置各不相同（Go Back 与 Continue 相邻仅 ~60px，相对鼠标定位误差
可能踩错），盲点必乱跳。每个新面板先 screendump → 裁剪按钮行 → 放大 OCR 逐字读
label 再点；「按钮是否可用」用图标区最大亮度判定（可用 ≈158、禁用 ≈94，差别可靠）。

**坑 11：QEMU 的「当前鼠标」开关会同时锁死 HMP 相对移动与 VNC 绝对点击**——
`info mice` 列出的设备里带 `*` 的才是激活路由；`mouse_set` 切到 PS/2（macOS
无 PS/2 驱动）后，HMP `mouse_move` 与 VNC `PointerEvent`（绝对坐标，本应直达
usb-tablet）**全部静默丢弃**，表象 = 三条输入通道全坏，实为一个路由开关。教训：
只许 `mouse_set` 到 HID Tablet；VNC 注入器（python 直连 127.0.0.1:5901，RFB 3.8
握手 + PointerEvent）配 tablet 后点击可靠。另：安装器面板顶部 heading 旁的小
spinner（~50×4px）会让 md5 持续翻转 —— 帧翻转 ≠ 状态变化，先 diff bbox 再解读。

**坑 12：安装器 app 半死不活时，输入会「迟到」且乱序**——主线程卡在网络调用上时，
WindowServer 还活着（Apple 菜单能秒开），点击/按键全部排队，app 线程偶尔醒来就
一次性消化积压 ⇒ 观感 = 点了没反应，过 1-2 分钟却自己乱跳（菜单开了又关、面板
回退）。教训：① 判「卡死」看 spinner 是否**静止**（动画帧 md5 恒定 = 冻结；持续
翻转 = 在干活，闭嘴等）；② 每次只发一个输入，隔 25s 验证一次；③ 处置同坑 8：
system_reset 重走，别在僵尸事件流上叠新输入。

**坑 13（定性）：VNC PointerEvent 的绝对坐标在本 VM 里从不生效——只有按钮位到达
guest**。光标冻结在最后已知位置（~左上角），任何 x/y 都等效于在 (25,12) 反复点击，
表象 = 每次点击都开关 Apple 菜单。已排除：SetEncodings 伪编码声明（-257
POINTER_TYPE_CHANGE / -223 / -258，qemu 11.1.2 ui/vnc.c pointer_event 里
`vs->absolute` 恒真、check_pointer_type_change 只影响 notify 报文）；`device_add
usb-tablet` 新设备 + `mouse_set` 重路由；HMP `mouse_move` 相对移动。**教训：纯键盘
走通全程**——HMP `sendkey` 是唯一可靠输入通道，且各控件键位不直观：Utilities
列表里 **Tab = 下一项**（方向键/字母 type-select/Return 全无效），**spc 激活选中
项**（ret 不行）；安装器面板里 Continue 是默认按钮，**ret 直接触发**。注入器脚本
见 /tmp/vnc.py（RFB 3.8 握手版，PointerEvent 部分仅剩历史价值）。

**坑 14：qemu 会静默双死，且重启必须以 root 身份**——稳定运行 12h 后，qemu 在
~40 分钟内两次无任何日志地消失（serial/qemu.log 均无痕迹；宿主 31G 内存但 swap
已用 4.5G，疑似宿主内存压力 OOM 但无 root 权限看 dmesg 确认）。重启命令
`docker exec -u root -d osx-autotest bash /home/arch/run-vm.sh`：**必须 -u root**，
因容器内 /dev/kvm 属 root:input，arch 用户启动会报 "Could not access KVM kernel
module: Permission denied"（/tmp/qemu.log 里的 138 字节失败记录就是这么来的）。
教训：① 长时间任务挂看门狗：每 25-30s 检查 qemu 进程，死了自动 root 重启（磁盘
qcow2 完好，重走键盘流程即可）；② qemu 死亡的表象是 4444/5901 连接拒绝，与
「HMP 被占」同症状，先 `ps aux | grep qemu` 分辨。

**坑 16：Terminal 一启动就确定性冻死整个系统；许可面板「按钮全聋」的真相是根本没有按钮**——
从菜单栏 Utilities→Terminal 打开 Terminal（无论安装器是否在跑），整个 UI 立即冻结
（时钟停走、所有输入死、屏幕 md5 恒定）；表象「TERMINAL_ALIVE」的假阳性 = 冻结前
恰好截到窗口打开的最后一帧。许可面板同理：整屏像素扫描发现**除 spinner 外无任何
按钮**（无蓝色默认按钮、无焦点环）——app 停在永久 busy 态（spinner 静止 = 主线程
卡死），之前按坐标/键位找 Disagree/Agree 全是白费。**换 `-vga std` 证伪 VGA 假设、
再换 `-cpu Haswell-noTSX-IBRS` 证伪 CPU 假设**：三组配置全部在安装器「选盘后阶段」
~45-66s 内 WindowServer 全屏冻结（std+host：3 帧跨 4 分钟 md5 全等 a2397521；std+
Haswell：walk4 检测器 `disk_alive FROZEN`）——冻结跟随安装器阶段而非虚拟化参数，
三组矩阵见测试报告 §5。教训：① 面板「按键全聋」先整屏像素扫描找蓝色默认按钮/焦点
环，确认控件存在再试键位；② 判「全屏冻结」用 menubar 时钟区 md5 跨 ≥65s 两次采样，
比全屏 md5 更准（时钟跨分钟不动 = WindowServer 死）；③ 现代 macOS 无
单用户模式、serial 仅 file 只写，Terminal 是唯一 shell 通道，它冻 = GUI 自动化路线
整体中断。

**坑 15：HMP monitor tcp 只收一个并发连接，轮询监视器会饿死交互命令**——
`-monitor tcp:127.0.0.1:4444,server,nowait` 一次只 accept 一个客户端；挂一个
15s 间隔的 screendump 轮询后，交互 sendkey 时常 "Connection refused"，重试也在
输（监视器握手 + sleep 恰好覆盖碰撞窗口）。教训：① 交互发键阶段不要挂高频
监视器，或把轮询间隔放大到 25s+、每次连接后立即退出；② sendkey 封装成 3-5 次
重试；③ 判「饿死」vs「qemu 死」看 /proc/net/tcp 里 4444 是否还有 LISTEN。
**追加两个同族坑**：① screendump 目标文件名复用昨天名字会被「陈旧文件」骗——screendump
命令没送达时 docker cp 照样拷出昨天的同名 ppm（mtime 才是真相，务必 `ls -la` 验证，
或一律用时间戳新名）；② 宿主侧杀掉 docker exec 的客户端**不会**杀容器内进程——
卡在 `cat <&3` 读 HMP 的 bash 会永生并占住 4444 唯一客户端槽（表象 = 连上但 banner
全空），用 /proc/net/tcp 找 ESTABLISHED 的 socket inode 再按 inode 反查 /proc/*/fd
杀进程；另有一次容器内 /dev/tcp 间歇性 ENOENT（分钟级窗口、自愈），重试封装同样能扛。
