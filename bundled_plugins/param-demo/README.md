# 参数演示（param-demo）

ZenTray 内置示例插件，演示 **命名入参（v2.1）** 全链路：

- 托盘点击 → **参数弹窗**（预填 参数预设 → manifest 缺省值，可修改后运行，取消即中止）
- 两个入参：`message`（文案，缺省 `你好`）、`times`（次数，缺省 `3`）
- 运行摘要（`RESULT ok`）回显所填值，可直观核对弹窗改动生效
- 每次运行向插件数据目录 `数据目录/plugin_data/param-demo/history.log` 追加一行——
  演示 `ZENTRAY_PLUGIN_DATA_DIR` 持久化（zip 覆盖重装不丢）

## 依赖 / 权限

- bash；无外部依赖，无需 root
- 手动复制改造：改 `id`/`name`/`params` 与 `run.sh` 即可

## 自测

托盘「🧩 插件 → 📜 脚本 → 参数演示」改参数运行，通知摘要应显示新值；
`~/.local/share/ZenTray/plugin_data/param-demo/history.log` 应出现该次记录。
