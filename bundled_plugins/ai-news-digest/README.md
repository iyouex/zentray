# ai-news-digest · AI 资讯日报

聚合免费公开源，生成**带图 HTML 日报**。零依赖（仅 Python 标准库）、零 API key 即可运行。

## 用法

- 手动：托盘 → 🧩 插件 → AI 资讯日报 → ▶ 运行（可填条数 top_n）
- 自动：随所关联任务的弹窗时刻运行（建一条周期任务并关联本插件即可定时跑）
- 报告：`数据目录/plugin_data/ai-news-digest/reports/YYYY-MM-DD.html`（浏览器打开）
  图片缓存在同级 `img/`，离线可看
- **分类**：条目按标题关键词分为 🤖 AI / 📱 数码 / 🌍 时政 三组分区展示，
  落空回退该源默认分类
- **详情页**：每张卡片整体可点，进入同目录 `detail-<日期>-<序号>.html`：
  中英对照图文长摘要（按钮切换中文/英文在前）、原文出处（文章链接 + 来源主页）、
  HN 讨论链接、同分类相关资讯互链，左上角返回日报

## 聚合源（2026-09 实测可用，免 key）

| 源 | 形态 | 说明 |
|----|------|------|
| Hacker News | [Algolia JSON API](https://hn.algolia.com/api) | 近 48h 含 "AI"、默认 ≥30 分 |
| TechCrunch AI | RSS | 人工编辑筛选 |
| The Verge AI | RSS | |
| MIT Tech Review | RSS | |
| 量子位 | RSS | 中文源 |
| The Verge 主站 | RSS | 数码类 |
| BBC 中文 | RSS | 时政类 |

机器之心（jiqizhixin）RSS 已被其重定向墙挡住，未收录。
VentureBeat 偶发 429 限流，失败只降级为报告里的 ⚠ 标注。

## 图片

各源 RSS 均无图片附件，按 lead-image 方案抓文章页 `og:image`（兜底
`twitter:image` / 首个内容 `<img>`，过滤 logo/icon/svg/data:），下载到本地
（≤2MB，魔数校验，最多 8 张）。

## 可选 AI 摘要 / 中英对照

把 `config.example.json` 复制到
`数据目录/plugin_data/ai-news-digest/config.json`：
- `"ai_summary": true`：仅发送「来源 ─ 标题」列表（不含任何凭证）到
  OpenAI 兼容端点生成 150 字中文主线摘要。
- `"bilingual"`（默认 `true`，需已配 AI 密钥）：**一次** AI 调用批量把全部
  标题+正文译成另一语言（中文→英文 / 英文→中文）。日报卡片标题一律以
  **中文为主**，另一语言以「译」行对照；详情页标题与正文双语成对展示，
  按钮切换哪种语言在前。

密钥取 `AI_API_KEY`/`AI_API_BASE_URL`/`AI_MODEL_NAME` 环境变量，
否则 settings.json 的 AI 活跃 profile。两者失败都自动降级，不影响报告。

## 配置键（均可省略）

| 键 | 默认 | 说明 |
|----|------|------|
| window_hours | 48 | 只收最近 N 小时 |
| top_n | 12 | 报告条数（同名入参优先） |
| min_hn_points | 30 | HN 最低分 |
| max_images | 8 | 最多抓图条数 |
| ai_summary | false | 生成 AI 摘要 |
| bilingual | true | 标题/正文中英对照，日报标题中文为主（需 AI 密钥，失败降级仅原文） |
| extra_rss | [] | 追加自定义 RSS/Atom URL 列表 |

## 自测

```bash
python ai_news_digest.py --selftest   # 34 项离线断言（fetch/post 全注入）
```
