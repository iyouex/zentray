# Windows 模拟环境调研 + 自动化测试报告（2026-10-07）

> 目标：在 Ubuntu 宿主机上调研并安装最佳 Windows 模拟环境，在其中对 ZenTray **Windows 实现**（`feature/win-taskbar-center` @ `f2e228e`，含 `feature/windows-support` 全部底座）执行自动化测试。
> 测试载荷：`zentray-win.tar.gz`（208KB，源码 + tests + pyproject，剔除 .git/venv/node_modules/dist）。

## 1. 调研（GitHub）

| 方案 | ⭐ | 结论 |
|---|---|---|
| **dockur/windows** | **53,542** | ✅ 选用。KVM 直通 + QEMU，Docker 一条命令拉起；ISO 从 **Microsoft 官方服务器**自动获取（无第三方镜像信任问题）；无人值守全自动安装；`/oem`+`install.bat` 与 `/shared`→`Z:` 双向文件交换为官方内建自动化机制 |
| WinBoat | 较小 | ❌ 本机 2 个月前用过（残留 11G `/home/iyoukai/winboat`，容器 WinBoat 已退出、VERSION=custom）。私有 boot 链维护弱于 dockur，不复用 |
| QEMU/virt-manager 手动装机 | — | ❌ 全手动，无自动化内建，等价于 dockur 的底层但零脚手架 |
| VirtualBox | — | ❌ Oracle 内核模块与主机内核版本强耦合（本机 7.0.0-34 内核），重且慢 |
| Wine/CrossOver | — | ❌ 翻译层非虚拟机，win32 行为非真实内核语义，不能作为验收依据 |

选型依据（本机实测证据）：`/dev/kvm` 可用（kvm 组）、763G 空闲磁盘、31G 内存、镜像 `ghcr.io/dockur/windows:5.14`（534MB）本机已在库。

**与 macOS 侧（Docker-OSX）关键差异**：macOS Recovery 镜像被 Apple CDN 对本机 IP 限流（1MiB 精确截断）；Windows ISO 走 Microsoft 官方 CDN **不限**，本机实测 ~12MB/s 直下。VM 路线在 Windows 侧可全程跑通。

## 2. 环境安装（Ubuntu 宿主机）

```bash
docker run -d --name zt-win-test \
  --device /dev/kvm --device /dev/net/tun --cap-add NET_ADMIN \
  -e VERSION=10l -e RAM_SIZE=8G -e CPU_CORES=4 -e DISK_SIZE=64G \
  -e USERNAME=zt -e PASSWORD=<测试机一次性口令> \
  -p 127.0.0.1:8006:8006 \
  -v /home/iyoukai/zentray-win-vm/storage:/storage \
  -v /home/iyoukai/zentray-win-vm/shared:/shared \
  -v /home/iyoukai/zentray-win-vm/oem:/oem \
  --stop-timeout 120 ghcr.io/dockur/windows:5.14
```

> ⚠️ `DISK_SIZE` 首版用 32G **不够**：LTSC 装机 ~12G，首启 Windows Update 两轮重启再吃 ~15G+，盘满后 guest 内所有文件写入**静默失败**（详见 §3.1 翻车 3），测试流水线全灭。测试盘至少 64G。
> ISO（4.9GB）dockur 装完后**多数时候**自动清理（重装需重新下载 ~6 分钟）。⚠️ 偶尔残留的缓存 ISO **不可直接复用**：`$OEM$`（/oem 载荷）只在**下载轮**嵌入 ISO，复用缓存 ISO 时 dockur **不会重新嵌入**——改过 install.bat 后若沿用旧 ISO，guest 跑的仍是旧脚本（v4b 翻车实证：setup-log 首行还是 `install.bat v3 start`）。改载荷重装必须 `rm storage/*.iso` 一并删掉。

- `VERSION=10l` = Windows 10 Pro LTSC（4.6GB，最小 SKU；含全部 win32 API——winreg/winuser/ctypes 路径与 Win11 一致；Win11 任务栏特有交互不在单测覆盖范围，见 §6）
- 所有端口仅绑 `127.0.0.1`（8006 为安装期网页查看器，测试全自动化不需要连它）
- 启动日志首个 `ERROR: Windows server download page gave us no download link!` 为其备用获取路线（评估版页面）失败，自动回退官方直下，**非故障**

## 3. 自动化机制（零 SSH/RDP 交互）

### 3.1 设计链路（dockur 官方机制，实测 6 处翻车）

1. **装机末步自动执行**：宿主机 `/oem` → 嵌入 ISO `$OEM$` → 虚拟机 `C:\OEM`；unattend 的 FirstLogonCommands 执行 `cmd /C if exist "C:\OEM\install.bat" start ... C:\OEM\install.bat`（镜像源码 `/run/define.sh` + `/run/assets/win10x64-ltsc.xml` 实证）
2. **结果回流**：宿主机 `/shared` ↔ 虚拟机 `Z:`（容器内 samba `\\20.20.20.1\Data`，共享名是 **Data**，guest 免密）
3. **翻车 1（v1 空跑）**：install.bat 在首登阶段执行，彼时 **Z: 尚未映射**；cmd 的重定向目标不存在会导致命令本身不执行——v1 全部输出重定向到 `Z:\`，故 45 分钟后 shared/ 全空、一行日志都没有
4. **翻车 2（v2「未执行」误判）**：v2 改为本地 `C:\OEM\out\` 落盘 + HTTP 直推 + Z: 兜底，32G 轮重装后看似无任何输出（incoming/shared 双空），当时误判为 $OEM$ 嵌入失败。**后经 64G 重装同版 v2 复跑翻案：机制本身正常**（22:19 自动执行、HTTP 推送全部落地）——32G 轮的「未执行」实为翻车 3 盘满静默失败的一部分
5. **翻车 3（磁盘满，32G 轮真正根因）**：32G 盘被首启 Windows Update 吃满 → guest 内一切写入静默失败——`mkdir` 能建目录但所有 `>` 重定向不落字节、下载全灭，且 cmd 不报任何错（`dir C:\` 尾行 0 字节可用才定位）。修复：`DISK_SIZE=64G` 重装
6. **翻车 4（cd 致命 bug，v1/v2/run.bat 共有）**：载荷 tar 包内 `tests/` 与 `zentray/` 是**兄弟目录**，脚本一律 `cd C:\zentray` 后 `pytest tests/unit` → `file or directory not found: tests/unit`，exit=4、0 个测试执行。修复：解包到 `C:\` 后 **`cd /d C:\`** 再跑（rootdir 必须是 pytest.ini/pyproject.toml 所在的解包根）
7. **翻车 5（v3 依赖不全）**：pip 只装 PySide6+pytest，14 个测试文件 import 失败（requests/pyzipper/injector/PyYAML），`Interrupted: 14 errors during collection`——207 个已收集测试**一个都没跑**。修复：v4 按项目 `pyproject.toml` 装全依赖
8. **翻车 6（缓存 ISO 载荷污染）**：v4 只改了 /oem/install.bat 的 pip 行，复用 storage/ 里残留的 ISO 重装——结果 guest 执行的还是**旧 v3 脚本**（setup-log 首行 `install.bat v3 start`、14 个依赖错误原样复现）。$OEM$ 只在 ISO 下载轮嵌入，复用不重嵌。修复：`rm storage/*.iso` 强制重新下载
9. **附加发现**：VM 到达桌面后约 20 分钟空闲发生一次**自发干净关机**（exit 0，LTSC eval + dockur 组合，疑与盘满/WU 相关，未深究）；容器重启后 autologon 正常回桌面，但 **Z: 不重挂**，需手动 `net use Z: \\20.20.20.1\Data`；samba 挂载约 30-40 分钟后可能自动断连。WU 重启风暴后 guest 网卡还会**单向死亡**（容器→guest ping 通、guest→容器全断，`ipconfig /release & /renew` 偶尔能救）——HTTP 回传失败先怀疑这个，别急着改链路

### 3.2 最终链路（OEM install.bat 全自动 + HTTP 直推，v3 起两轮实证）

```
宿主机                                VM (真实 Win10 19044)
------                                ---------------------
/oem/install.bat + zentray-win.tar.gz ←(dockur 装机末步自动执行, 管理员权限)
  ① python.org 3.12.10 AllUsers 静默安装 (~30s)
  ② tar -xf C:\OEM\zentray-win.tar.gz -C C:\  → C:\{zentray,tests,pyproject.toml,pytest.ini}
  ③ cd /d C:\ + pip install PySide6 pytest requests pynput injector pyzipper PyYAML
  ④ 环境取证 → env.txt / winver.txt
  ⑤ QT_QPA_PLATFORM=offscreen + python -m pytest tests/unit -q → pytest-output.txt
  ⑥ 出口1(主): curl -T → http://172.17.0.1:8765/（宿主接收器，双网关×3轮×30s间隔）
     出口2(兜底): copy → Z:\（samba）
  ⑦ DONE.txt("exit=N") 哨兵 → 宿主机轮询 incoming/ 得知完成
```

- 宿主机接收器：`zentray-win-vm/receiver.py`，stdlib 25 行，PUT 落盘 `incoming/`，**仅绑 172.17.0.1**（docker 桥网关，不对局域网暴露）。**guest→宿主 HTTP 实测可达**（两轮全量推送落地；早先「guest 侧 HTTP 不通」是误判——不通只发生在盘满 / WU 风暴后网卡单向死亡时，见 §3.1）
- 整轮耗时：重装 ~15.5 分钟（ISO 命中缓存则 ~10 分钟）+ install.bat ~2-5 分钟，全程零交互
- **备用通道（VNC 键盘注入）**：dockur 容器内监听 5900（不发布宿主机），`alpine/socat` 中继到 `127.0.0.1:15900` + `vncdotool`（python:3.12-slim 容器内装，宿主机零依赖）。用于观察桌面/应急注入，但**打字在慢速 autologon 与 WU 风暴期会整段丢失**，且屏幕读数多次幻觉——自动化结论只认宿主侧工件（receiver.log / shared/ / 盘取证），不认截图转述
- **无 root 盘取证**：`pytsk3`（pip 可装）用户态直读 `storage/data.img` NTFS（GPT #6 分区，偏移 526336×512）；qemu 写缓存导致活盘读滞后，需先 `docker stop` 再读

## 4. 测试结果（VM 内真实 Windows 内核，v4b 轮 · 2026-10-08 00:10）

| 环境项 | 值 |
|---|---|
| 宿主机 | Ubuntu（内核 7.0.0-34），KVM 直通：Intel Core 5 220H · 4 vCPU · 8G RAM |
| 虚拟化 | dockur/windows 5.14（QEMU 10.0.6，64G raw 盘） |
| Guest OS | Windows 10 Pro LTSC eval，**10.0.19044.1288**（真实内核，非翻译层） |
| Python | 3.12.10（MSC v.1943，64-bit AMD64，AllUsers 静默安装） |
| 依赖 | PySide6 6.11.2 + requests / pynput / injector / pyzipper / PyYAML（按 `pyproject.toml` 全量） |
| 测试框架 | pytest 9.1.1 + pluggy 1.6.0，`QT_QPA_PLATFORM=offscreen` |
| 被测代码 | `feature/win-taskbar-center` @ `f2e228e`（叠加 `feature/windows-support` 全底座） |

**结果：`collected 349 items`（与 Linux 基线完全一致，无收集缺失/跳过）—— 325 passed / 24 failed / 0 error，10.43s，exit=1。** 整轮零人工交互 14 分 04 秒（含 ISO 重新下载 ~6 分钟；setup-log：install.bat v4 00:07:56 → pip 全依赖 59s → pytest 10.43s）。

### 失败 24 项分类（全部为真实跨平台缺陷，非 VM 环境噪音）

| # | 类别 | 数量 | 测试 | 现象 | 根因初判 | 修复归属 |
|---|---|---|---|---|---|---|
| A | 插件运行时跑不动 `.sh` | **14** | `test_plugin_runtime.py` 全部失败（run_sample_script / service_status / result_fail_vetoes / exit1_vetoes / result_text / no_result_defaults / meta_json / task_env_injection / task_env_sparse / plugin_data_dir_env / param_values / param_defaults / param_preset / silent_hang） | `OSError: [WinError 193] %1 is not a valid Win32 application`（或 run 返回 False 连坐） | 插件 entry 是 shell 脚本，Windows `CreateProcess` 不能直接执行无 PE 头文件；`plugins/runtime.py` 直接 `subprocess` 裸调 entry | **通用层设计缺陷**：执行器需按平台分派（`cmd /c` / `sh -c` 包装，或插件清单声明平台 entry）——按三平台规则收敛到平台层 |
| B | 插件校验器路径分隔符 | 4 | `test_plugin_install_api.py`：validate_bundled_net_cleanup / validate_bundled_param_demo / reject_outside_home / plugins_list_v21_metadata | 400≠200；`路径不存在: C:\etc`（期望「允许范围」报错）；列表 KeyError `'net-cleanup'` | 校验器按 `/` 分隔假设写死，Windows 反斜杠路径全被拒；内置插件校验不过 → 不入列表 | 通用层：manifest/校验器路径归一化（`PurePath` 化） |
| C | 内置插件编辑/删除连坐 | 3 | `test_plugin_bundled_edit_delete.py`：update_copies / update_rejected / delete_hides | 404≠200/400，`插件不存在或校验未通过` | B 的下游：内置插件校验失败未进注册表 → 编辑/删除自然 404 | 随 B 修复自动恢复 |
| D | 托盘饼图图标生成 | 1 | `test_menu_builder.py::test_break_icon_generation` | `_generate_pie_icons_into` 返回 False | 番茄钟「休息」饼图图标在 Windows 下生成失败（QIcon/QPixmap 写出路径） | `feature/windows-support` 托盘层 |
| E | 运维报告扩展名/路径 | 1 | `test_plugin_run_report_md.py::test_open_html_report_directly` | 期望 `...\r.html` 实得 `...\ops_runs\....md` | 报告「直接打开 html」分支在 Windows 落成了 md 路径 | 通用层：报告路径策略平台不一致 |
| F | 任务服务读文件编码 | 1 | `test_task_service.py::test_subtask_done_auto_completes` | `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` | 子任务完成回读用 locale 默认编码（cp1252）而非 utf-8 | 通用层：`open(..., encoding="utf-8")` 一行修 |

**判读**：依赖导入 / DI / 存储 / 路径 / Qt offscreen 等底座在真实 Windows 内核上**全绿（325 项）**；24 项失败集中在插件子系统（A+B+C = 21 项，两条根因）加 3 个孤立点（D 饼图图标、E 报告扩展名、F 编码）。对照 Linux 全绿基线，此 24 项即 `feature/win-taskbar-center` 的 **Windows 修复清单**。

## 5. 已知边界与未覆盖项

- **Win11 专属行为**未覆盖（任务栏「从不合并」注册表 `TaskbarGlomLevel` 读取在 10 上语义相同、单测可测；但 Win11 23H2 真实任务栏渲染/中央按钮占位需真机或 `VERSION=11` 人工验收）
- **打包链**（PyInstaller Windows 产物、Inno Setup）未在本轮执行——单测验证的是代码路径，产物级验证建议交给 GitHub Actions `windows-latest`
- GPU/多显示器/HiDPI 场景不在单测范围

## 6. 建议

1. **修复清单落地**：§4 的 24 项失败按归属修——A（插件执行器平台分派）与 B（校验器路径归一化）是两条主根因（覆盖 21 项），D 归 `feature/windows-support` 托盘层，E/F 是通用层一行级修复；修完用同链路（§2 docker run + §3.2，14 分钟一轮）回归
2. **CI**：真 Windows CI 走 GitHub Actions `windows-latest`（免费、正版、无 CDN 限制），跑同一套 `pytest tests/unit`；本机 dockur VM 作为**本地验收兜底**（一次装好后 `docker start zt-win-test` 秒级复用，VM 盘在 `/home/iyoukai/zentray-win-vm/storage`）
3. 需要图形验收（速览面板/中央按钮真实渲染）时：`docker run` 同配置改 `VERSION=11`，或直接 `xdg-open http://127.0.0.1:8006` 观看/接管现有 VM
4. 回收：测试数据盘 64G，确认不再需要后 `docker rm -f zt-win-test && rm -rf /home/iyoukai/zentray-win-vm/storage`；docker 镜像（534MB）建议保留
