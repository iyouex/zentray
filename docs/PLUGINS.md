# ZenTray 插件系统规范文档

**版本**：v2.1  
**日期**：2026-08-05  
**作者**：Grok  
**状态**：已完成设计

---

## 1. 插件系统概述

ZenTray 插件系统是一套**高度可扩展**的插件框架，旨在让用户（尤其是开发者）轻松编写和使用**脚本插件**和**服务插件**。

插件分为两类：
- **内置插件**（官方提供）
- **用户插件**（用户自行编写）

插件必须经过**强格式校验**才能上线。

---

## 2. 插件目录结构

- **内置插件**：固定在 `bundled_plugins/official/`（不可更改）
- **用户插件**：用户可自行添加本地路径（支持拖拽文件夹）

---

## 3. 插件格式规范

必须包含以下字段：

```yaml
id: unique-plugin-id
name: "插件名称"
version: "1.0.0"
type: script | service
api_version: 1

entry: "main.js" | "main.py" | "main.sh"
args: []                           # 启动参数
workdir: "sub/dir"                 # 可选
timeout_sec: 60
description: "插件说明"
```

---

## 4. 校验机制

三阶段强校验：

1. 格式校验
2. 静态检查
3. 动态运行时检查

---

## 5. 执行入口设计

推荐命令：
- `node main.js [args]`
- `python main.py [args]`
- `./main.sh [args]`

---

## 6. 使用手册

### 内置插件
位于 `bundled_plugins/` 目录下，直接启用。

### 用户插件
1. 创建用户插件目录：`DATA_DIR/plugins/user/`（DATA_DIR=~/.local/share/zentray/）
2. 放置 `plugin.yaml` + entry 脚本
3. 插件 id 必须符合 `[a-z0-9]+(-[a-z0-9]+)*`

示例已放置于 `tests/fixtures/plugins/teams-cache-cleanup/`，复制到用户目录后即可使用。

### 启用方式
- 通过 API `/api/plugins/refresh` 或托盘菜单开关
- 禁用插件不会影响内置功能

---

## 7. 常见问题

- 确保 entry 可执行：`chmod +x cleanup.sh`
- 缓存清理适合在启动时自动运行
- 支持备份缓存目录

---

## 8. 贡献指南

鼓励用户把自制插件上传贡献成为社区插件。

---

**文档来源**：基于用户需求 v2.1 设计
