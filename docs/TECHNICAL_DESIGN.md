# ZenTray 插件系统技术设计文档

**版本**：v2.1  
**日期**：2026-08-05

---

## 1. 插件目录结构

```
bundled_plugins/official/          # 内置插件（固定目录）
user_plugins/                      # 用户插件（可自定义多个目录）
```

---

## 2. 插件格式规范

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

## 3. 校验规则（三阶段强校验）

1. 格式校验
2. 静态检查
3. 动态运行时检查

---

## 4. 执行入口设计

推荐执行命令：
- `node main.js [args]`
- `python main.py [args]`
- `./main.sh [args]`

支持特性：
- 静态参数传递
- 运行时参数修改弹窗
- 超时保护
- 日志输出必须简短 + 截断

---

## 5. API 接口

- `GET /api/plugins` → 获取所有插件列表
- `POST /api/plugins/validate` → 校验单个目录
- `POST /api/plugins/install` → 安装用户插件
- `DELETE /api/plugins/{id}` → 删除插件
- `POST /api/plugins/refresh` → 强制刷新列表

---

## 6. 前端实现建议

- Vue Settings.vue
  - 用户插件目录选择器
  - 总开关 + 用户插件开关
  - 插件列表（支持关闭/删除）
  - 参数弹窗
  - 滚动日志查看窗口

---

## 7. 后端实现建议

- 使用 `runtime.py` 执行插件
- 使用 `manifest.py` 进行强校验
- 提供子进程隔离和超时保护

---

## 8. 文档位置

- `docs/PLUGINS.md` —— 插件规范
- `docs/USER_MANUAL.md` —— 使用手册
- `docs/TECHNICAL_DESIGN.md` —— 技术设计文档

---

**文档来源**：基于用户需求 v2.1 设计
