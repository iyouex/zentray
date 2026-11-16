# 文本工具箱重设计（2026-11-12）

> 痛点：粘贴大文本后 SQL/JSON/文本比对显示失调或溢出；文本框高度、滚动条、页面布局混乱。

## 选型结论

- **编辑器基座：CodeMirror 5.65.16（CDN + 降级）**——与既有 jsonrepair / sql-formatter 同模式
  （`onerror` 标记 → 保留现 textarea UI 降级）。CDN 四件已验证 200：
  lib/codemirror.min.js、mode/sql、mode/javascript、theme/material-darker.min.css。
  - 对症性：CM 视口虚拟渲染（只画可见行）直接解决「大文本 DOM 爆炸」；自带行号/折叠/主题，
    替换手搓 gutter（.jl-gutter）与裸 textarea。
  - 否决 Monaco（~2MB+ loader 体系，离线降级路径太重）、ACE（同量级但生态趋冷）、
    纯 textarea 补 CSS（用户已要求按好工具重设计，且大文本性能无解）。
- **文本比对**：保留 v0.7.20 融合框（输入即比对/底衬叠层/贝塞尔连线），专项修大文本缺陷，
  不引入 CM（双栏叠层透明 textarea 结构是其核心，CM 无法叠透明输入层）。

## 布局体系（全工具统一）

- 页面级：`main` 保持纵向滚动，但所有**编辑/输出容器**一律进入 pane 体系：
  `height: clamp(280px, 56vh, 70vh)`，内部滚动，永不撑破页面。
- 输出/消息区（.msg / .kv / 结果 pre）：`max-height: 40vh + overflow:auto`，大结果内滚不外溢。
- 溢出判据（Playwright oracle，进 tests/）：粘贴 1MB 文本逐工具操作后，
  `document.documentElement.scrollWidth <= innerWidth`（零横向）、
  body 纵向增长有界（≤ 视口 3 倍）、各 pane 自身可滚。

## 子任务拆分（逐个提交）

| # | 子任务 | 内容 |
|---|---|---|
| 1 | 布局基座 | pane 高度体系 + 输出区钳制 + 大文本溢出 oracle（六工具） |
| 2 | JSON 工具 | in/out 迁 CM(json)（CDN 降级 textarea），拆手搓 gutter，10k 行性能断言 |
| 3 | SQL 工具 | in/out 迁 CM(sql + 方言)，结果区同基座 |
| 4 | 文本比对 | 大文本专项：行号/连线错位、5k 行同步滚动、水平溢出、等高钳制 |
| 5 | 输出区规整 | crypto/random/time 的 kv/msg/结果块统一内滚 + 复制 |
| 6 | 文档 | README 功能矩阵 + 降级说明 |

每步：改 → Playwright 实测 → 源码级回归测试 → 全量 pytest 绿 → 独立提交。
分支：`feature/toolbox-redesign`（自 staging）。
