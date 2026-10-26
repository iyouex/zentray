# 文本工具箱（text-toolbox）

ZenTray **service** 类型插件：面板 ▶ 启动 → 起本地 Web 服务并自动打开页面；
⏹ 停止 → 干净退出（关监听、释放端口）；ℹ 状态 → 报运行状态与 URL。

## 功能（页面内六个标签，全部前端完成）

| 工具 | 能力 |
|------|------|
| JSON | 照搬 jsonlint.com 设计：单编辑器实时校验（绿/红横幅 + 行列定位 + 源行 `^` 指针 + 行号槽错误行红标）、Prettify⇄Compress（2/4/Tab 缩进）、Copy、Try Fix（jsonrepair CDN，降级内置启发式）、Load Sample、Ctrl+Enter / Ctrl+Shift+F 快捷键、拖文件载入、Valid JSON 统计（大小/键数/深度/对象/数组） |
| SQL | 格式化（sql-formatter，mysql/hive/spark 方言）、压缩（去注释单行）、简单语法检查（配平+关键字粗检） |
| 文本比对 | Mergely 深色双栏合并视图（照搬 jq22/textDifference 设计）：输入即比对（融合框：输入与结果同框呈现，软换行自适应宽免横向拖动）；中缝连线 + 每差异块 ◀/▶ 合并箭头；行内词高亮（CJK 逐字/西文按词，可切全逐字），拖拽读文件（路径标签显示文件名），ignore witespaces/忽略大小写，两侧 保存save 下载（含已接受合并），相似度（字符级 LCS / max 字符数） |
| 时间工具 | 单标签内二级页：**万年历**（公历+农历 1900–2100 码表、干支生肖、节气 ±1 分钟、节日、国务院休/班角标 2020–2026；点日看详情卡，右侧列出**当日任务**——截止日命中或提醒槽命中，读 `/api/tasks`）；**三合一页**（时间戳⇄时间：方向按钮切换，秒/毫秒下拉选择或位数自适应识别，本地/ISO/UTC/相对/星期·ISO 周/年积日；日期计算：加减（月末 clamp）+ 时间差（自然 Y年M月D日 + 合计 + 工作日）；格式化：25 种格式逐行复制，本地/UTC 切换）。所有日期时间输入为**分段式**：每单位一格（YYYY·MM·DD·HH·mm·ss），输满自动右移到下一格，退格回退，粘贴完整时间串自动分布 |
| 随机字符串 | 长度/字符集勾选/排除易混字符/前缀，crypto.getRandomValues + 拒绝采样 |
| 哈希/编码/加密 | MD5、Unicode \uXXXX、URL 百分号、AES-256-GCM（WebCrypto，PBKDF2 派生，base64 含 salt+IV） |

## 架构与安全

- 服务端 = Python3 标准库（http.server.ThreadingHTTPServer），零 pip 依赖。
- 只绑 `127.0.0.1`；默认端口 18767（可用 env `TEXT_TOOLBOX_PORT` 改），被占自动 +1 重试至多 10 次。
- HTTP 仅 GET：`/`（页面）、`/healthz`（探活）、`/api/tasks`（读 `DATA_DIR/active_tasks.json`
  的只读投影：title/deadline/category/reminder；读取失败返回 `[]`）、`/favicon.ico`；
  无任何写文件/执行命令端点。
- 页面下发 CSP（允许 cdnjs/jsdelivr/unpkg 的 script-src）与 `X-Content-Type-Options: nosniff`。
- 前端为单个自包含 index.html；仅两处 CDN `<script>`（jsonrepair、sql-formatter），加载失败自动降级并提示。
- 自动开浏览器仅在服务启动端口就绪后发生一次（Linux 走 xdg-open）。
- 状态文件/pid 与 daemon 日志写在 `ZENTRAY_PLUGIN_DATA_DIR`（无该环境时回落
  `~/.local/share/ZenTray/plugin_data/text-toolbox/`），不写插件自身目录。

## 依赖与权限

- Python ≥ 3.8 标准库；页面可选 CDN（离线仍可用降级功能）。
- 无需 root；仅本机回环监听与 xdg-open。

## 自测（全部可离线复跑）

```bash
# 1) 规范校验（仓库根）
./venv/bin/python scripts/validate_plugin.py ~/.local/share/ZenTray/plugins/text-toolbox

# 2) 服务级 selftest（起服务、端口占用换端口、锚点、SIGTERM 释放、start/stop/status 链路）
python3 text_toolbox.py selftest

# 3) 前端纯函数自测（node ≥ 19；含 md5/json 修复/diff/时间戳/随机串/unicode/AES 回路
#    + 农历春节向量×27/节气/节假日/日期加减差值/25 格式向量）
node tests/frontend_core_test.mjs

# 4) AES/MD5 跨实现对照（需 pip cryptography，仅自测用）
python3 tests/cross_check.py && node tests/frontend_core_test.mjs --verify-py
```

## 已知限制

- SQL 语法检查为**非全量**校验：仅括号/引号配平 + 关键字 Levenshtein≤1 拼写粗检。
- JSON 修复的降级启发式只覆盖常见问题（尾逗号/单引号/裸键名/注释/Python 字面量）；
  CDN 可用时用 jsonrepair，能力强得多。
- 词级 diff 逐 token 高亮，行级 diff 为 O(n·m) LCS，超大文本（数万行）会慢；
  行数 >2 万或字符 >200 万时自动关闭词内高亮并跳过精确相似度。
- 「接受替换」按差异块独立应用（无冲突检测的三方合并 YAGNI）；相似度超 2500 字符/侧
  降级为行级口径（偏保守）。
- 比对组件复刻 jq22/textDifference 的 Mergely 视觉与交互，但无 CodeMirror/jQuery
  （约束：不加新 CDN）：编辑层为透明 textarea 叠顶结果底衬，边打字边
  （150ms 防抖）重比对，软换行自适应面板宽；站点 path 标签的 40px 字号按面板比例缩为 13px。
- JSON 页签复刻 jsonlint.com 深色主题（取色自站点 CSS：#0D0D0D/#1A1A1A/#2D2D2D 底、
  #0A84FF 主按钮、rgba(16,185,129,.1)/rgba(239,68,68,.1) 状态横幅、#32D74B/#FF453A
  编辑器描边环），但无 Monaco/Inter/JetBrains Mono（约束：不加新 CDN）：编辑器为
  textarea + 自绘行号槽，错误行以行号红标 + 源行 `^` 指针呈现（无编辑器内整行高亮、
  无语法着色）；字体走系统栈。校验引擎为浏览器 JSON.parse（单错误、无 E0xx 错误码
  体系，徽章展示 V8 错误名），Try Fix 引擎 jsonrepair@3 CDN（降级内置启发式），
  统计（大小/键数/深度/对象/数组）与站点 Valid JSON 横幅同口径。站点右侧 280px
  工具导航栏与 URL 载入输入框未复刻（本页签导航由顶部 tabs 承担；CSP 禁外联）。
- 时间戳 11 位数字在「自动识别」下按秒处理（歧义区间；可在下拉手动指定毫秒）。
- 「当日任务」按截止日 / 提醒槽（weekday 或 day_of_month）匹配；启用提醒但无槽位仅
  有每日时刻的按「每日提醒」计（每天命中）。数据快照自 active_tasks.json，不回写。
- 法定节假日数据覆盖 **2020–2026**（国务院通知人工录入）；范围外年份按周末回落，无休/班角标。
- 农历码表覆盖 1900–2100；节气为经典天文近似（±1 分钟内），非天文台历表。
- CSP 需 `'unsafe-inline'`（单文件内联 JS 的必然代价）；故 CSP 防的是外域脚本，不防页面自身。
