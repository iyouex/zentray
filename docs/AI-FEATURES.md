# AI 场景化能力（AI Everywhere）

> 分支 `feature/ai-everywhere`。目标：把 AI 从「每日计划/复盘」两个定时任务扩展为贯穿任务生命周期的按需能力，全部可在设置页独立开关，默认关闭（不配置不花钱、不误触发）。

## 1. 能力矩阵

| 能力 | 设置开关（`ai.features.*`） | 入口 | 接口 |
|---|---|---|---|
| 智能解析 | `smart_parse` | 快速添加 ✨ 按钮；任务表单「AI 解析」 | `POST /api/ai/parse` |
| 图片识别 | `image_ocr` | 任务表单上传区（点击 / 拖入 / 粘贴图片） | `POST /api/ai/ocr` |
| 任务建议 | `task_suggest` | 任务列表详情面板「AI 建议」 | `POST /api/ai/suggest` |
| 每日计划/复盘 | `plan.enabled` / `review.enabled`（既有） | 定时调度（既有） | 既有 |

三者的模型接入复用 `ai.api_profiles`（多 Key 单启用），无重复配置。

## 2. 交互设计

### 2.1 智能解析（文本 → 任务草稿）
- **快速添加**：开关开启后输入框右侧出现 ✨。点击 → 后端解析 → 展开预览卡（分类/优先级/截止/提醒/子任务 chips）→「确认添加」入库，「重新输入」收起。预览展开时**回车=确认添加、Esc=收起重新输入**；无预览时回车行为不变（直接快速入库）。
- **任务表单**：标题+详情已填时「AI 解析」按钮可用。结果以弹层逐字段预览，用户确认后应用到表单（分类按名称模糊匹配已有一级分类，匹配不上不动）。

### 2.2 图片识别（视觉模型 OCR → 任务草稿）
- 任务表单（新建与编辑同用）右卡顶部上传区：点击选择、拖入文件或直接 Ctrl+V 粘贴截图，选中后有缩略图预览。
- 后端将图片以 data URL 送视觉模型，可返回**多条**任务草稿；前端先选哪一条（列表），再走与 2.1 相同的字段预览 → 应用。
- 图片不落盘、不进附件，仅本次解析使用。

### 2.3 任务建议（全局任务列表 → 建议卡片）
- 任务列表「任务详情与操作」卡 header 的「💡 AI 建议」→ 后端把活跃任务摘要（标题/分类/优先级/截止/子任务数，**不含详情正文**）送模型。
- 返回建议数组，前端渲染卡片，每条可**应用**或**忽略**：
  - `priority`：直接改优先级（`PUT /api/tasks/{id}`）
  - `deadline`：设置/调整截止日
  - `split`：按建议拆子任务（逐条 `POST /api/tasks/{id}/subtasks`）
  - `review`/`clean`：纯文本建议（如「这 3 条已过期 5 天，建议今天集中清掉」），无自动应用

### 2.4 草稿 Schema（解析类接口统一返回）
```json
{
  "title": "发布季度版本 v0.6",
  "category": "工作",
  "priority": "high",
  "deadline": "2026-09-26",
  "reminder_time": "18:30",
  "details": "先灰度 10%……",
  "subtasks": ["过安全审计", "补 changelog"]
}
```
- 日期相对表达（“后天”“周五”）由模型结合**当日日期**换算为绝对日期；时间统一 `HH:MM`。
- `category` 返回名称，由前端对照 `meta.categories.primary_list` 匹配 id；匹配不上保持现状。

## 3. 后端设计

### 3.1 `zentray/services/ai_assist.py`（新）
- `AIAssistError`：携带 `feature` 与用户可读 message（无 Key / 功能未开启 / 网络失败 / 返回不合法）。
- `AIAssistService`：
  - `parse_text(text, category_names, today)` → draft dict
  - `parse_image(data_url, category_names, today)` → `{"drafts": [...]}`（1~5 条）
  - `suggest(tasks_summary, today, focus_title)` → suggestions list（focus_id 由路由层解析为标题传入）
- 共用 `_chat(messages, ...)`：OpenAI 兼容 `/chat/completions`；`temperature=0.2`；`max_tokens` 首档 4000、空响应（推理模型思考吃光预算）自动 4 倍重试一次；图片走 `image_url` content part；响应剥 ```` ```json ```` 围栏后 `json.loads`，失败即抛错。
- **Fake 模式**：环境变量 `ZENTRAY_AI_FAKE=1` 时三方法返回确定性 fixture（不联网），供自动化回归与无 Key 演示。

**厂商接入速查（Base URL）**：

| 厂商 / 套餐 | Base URL | 说明 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | 默认 |
| 智谱按量（API Key 充值） | `https://open.bigmodel.cn/api/paas/v4` | 按 token 计费 |
| **智谱 Coding Plan 订阅** | **`https://open.bigmodel.cn/api/coding/paas/v4`** | 订阅 Key 在标准端点报 1113「余额不足」，**必须**用此专属端点；`glm-5.3-flash` 为推理模型（思考计入 max_tokens，已由重试兜底） |

### 3.2 设置结构（`settings_manager.py`）
```python
@dataclass
class AIFeatureSettings:
    smart_parse: bool = False
    image_ocr: bool = False
    task_suggest: bool = False
```
挂到 `AISettings.features`；`_parse_ai` / `to_dict` 透传；旧 settings.json 无该键时取默认（全关）。`GET /api/meta` 增加 `ai_features` 字段，供非设置页轻量获取开关。

### 3.3 路由（`handlers.py`）
- `POST /api/ai/parse` `{text}` → 门控 `smart_parse` → `{draft}`
- `POST /api/ai/ocr` `{image: "data:image/png;base64,..."}` → 门控 `image_ocr` → `{drafts}`
- `POST /api/ai/suggest` `{focus_id?}` → 门控 `task_suggest` → `{suggestions}`
- 门控不通过返回 `403 {"error": "AI 功能未开启", "feature": "..."}`；参数缺失 `400`。

## 4. 设置页 IA 重构

左导航从 6 项重组为 7 项（图标 + 文字）：

| 新菜单 | 内容变化 |
|---|---|
| ✨ AI 能力 | **新**：顶部场景开关卡片网格（智能解析/图片识别/任务建议，各带说明）+ tabs（每日计划 / 每日复盘 / 模型接入） |
| 🔔 通知 | 从原「AI 与通知」拆出独立页（应用弹窗 / WxPusher 渠道） |
| 📋 任务 | 原「任务轮播」改名，含轮播节奏 + 逾期策略 |
| 🍅 番茄钟 | 保持 |
| 🏷️ 分类 | 保持（标题格式 + 分类树） |
| 🖥️ 系统 | 保持（外观/启动/数据迁移） |
| 📜 历史 | 保持 |

布局统一：所有页内容收进圆角 section 卡片；AI 场景网格为「图标 + 名称 + 一句描述 + 开关」的卡片行。

## 5. 测试与回归
- 单测：`tests/unit/test_ai_assist.py`（fake 三方法、围栏剥离、草稿归一化、路由 200/403/400 门控、settings features 序列化往返、dict 子任务回归）。
- 前端：`npm run build`；mock 双态服务器（开关全开 / 全关）+ DOM 断言截图（开启时按钮/预览/建议卡出现，关闭时对应元素 count=0）。
- 真机：`ZENTRAY_AI_FAKE=1` 起完整后端（真实 handlers + FileTaskRepository + 生产数据目录）走查三场景与 403 门控。

## 6. 隐私与成本边界
- 任务建议只送任务摘要（标题/分类/优先级/截止/子任务计数），不送详情正文与附件。
- 图片仅本次请求使用，不落盘。
- 三开关默认关闭；关闭时前后端相关 UI 不渲染、接口 403。
