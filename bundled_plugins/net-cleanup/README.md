# 网络清理（示例插件）

| 字段 | 值 |
|------|-----|
| id | `net-cleanup` |
| type | `script` |
| 入口 | `run.sh` |

## 做什么

在 **Linux** 上尽量执行只读/安全的网络侧清理：

1. `resolvectl flush-caches`（或 `systemd-resolve --flush-caches`）  
2. 若存在 `nscd`，刷新 hosts 缓存  
3. `ip route flush cache`（无权限时跳过并记日志）  
4. 打印当前 `http(s)_proxy` 等环境变量（**不修改**）  
5. 提示如何扩展公司 VPN / 代理脚本  

**不包含：** 自动连/断 VPN、改 Clash 配置、删浏览器数据、需要写死公司路径的逻辑。

## 使用

1. 设置 → **插件** → 启用，并打开 **加载内置插件**  
2. 托盘菜单 → **🧩 插件** → **网络清理（示例）**  
3. 顶栏显示 `⚡` 进度；结束后恢复任务轮播  

也可拷到用户目录单独维护：

```bash
cp -a bundled_plugins/net-cleanup ~/.local/share/ZenTray/plugins/
```

## 校验

```bash
python scripts/validate_plugin.py bundled_plugins/net-cleanup
```

## 自定义

复制本目录改 `id`/`name`，在 `run.sh` 中增加例如：

- 调用你的 VPN CLI  
- `systemctl --user restart xxx`  
- 清理你本机代理工具的缓存目录（请自行评估风险）  

务必保持 stdout 协议：`PROGRESS` / `LOG` / `RESULT`。详见 [PLUGIN_SPEC.md](../../docs/plugins/PLUGIN_SPEC.md)。

## 权限说明

| 步骤 | 权限 |
|------|------|
| resolvectl flush-caches | 通常普通用户可用 |
| nscd | 视系统配置 |
| ip route flush cache | 部分系统需要 root，失败会 SKIP |

应用不会代填 sudo 密码；若某步必须提权，请在插件内自行使用 `pkexec` 等。
