# 飞书通知渠道 —— 设计方案与可行性评估

> 状态：设计稿，未实现。目标：在现有 app_popup / WxPusher（及设计中的企业微信机器人）之外新增飞书群推送渠道。
> API 细节已对照官方文档核验（2026-10-07，[自定义机器人使用指南](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)）。

## 1. 选型：飞书群自定义机器人（Custom Bot Webhook）

「飞书通知」有三条常见路线，选第一条：

| 路线 | 结论 |
|------|------|
| **飞书群自定义机器人 webhook** | ✅ 采用。官方 API、免管理员审核（加群即用）、单一凭证（webhook URL）、一个 HTTP POST 完事；可选签名校验纯 stdlib 实现 |
| 飞书应用机器人（app_id/app_secret） | ❌ 需建应用 + tenant_access_token 获取与刷新 + 权限审批，为个人 GTD 推送属过度工程；仅当未来要做「单聊私推/读群消息」再考虑 |
| Server酱 / PushPlus 等中转 | ❌ 本质是另一个 WxPusher 式中间商，与现有渠道同质，无增量价值 |

### API 要点（官方 webhook，已核验）

- 端点：`POST https://open.feishu.cn/open-apis/bot/v2/hook/<token>`（token 即全部凭证；URL 整体等同密码，不可泄露）
- 报文：`{"msg_type":"text","content":{"text":"标题\n正文"}}`
  - 消息类型支持 text / post（富文本）/ image / share_chat / interactive（卡片）；**text 不渲染 markdown**，AI 报告按纯文本降级显示，可接受
  - 请求体上限 **20 KB**，超出报错
- 安全设置（强烈建议配其一，可多选）：自定义关键词（19024）/ IP 白名单（19022，个人电脑无固定 IP 不适用）/ **签名校验（本方案默认）**
- **加签算法**（官方 Python 示例即纯 stdlib）：
  ```python
  string_to_sign = f"{timestamp}\n{secret}"          # timestamp 为秒级、距当前 <1 小时
  sign = base64.b64encode(
      hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
  ).decode("utf-8")
  # 注意 quirky 点：key 是 string_to_sign，被签消息是空串
  ```
  开启后 body 须附 `"timestamp"`（字符串）与 `"sign"` 字段；失败返回 `{"code":19021,"msg":"sign match fail or timestamp is not within one hour..."}`
- 成功返回 HTTP 200 + `{"code":0,"msg":"success"}`（另含冗余 `StatusCode:0`，忽略）；**逻辑错误也返回 200**，必须检查 code
- 频控：单租户单机器人 **100 条/分钟、5 条/秒**；限流错误码 11232；官方建议避开整点/半点发送
- 机器人只在**本群**生效、无任何数据访问权限；接收方需飞书 App 且在该群内

## 2. 实现方案（镜像 WxPusher / wecom_bot 模式，全程零新依赖）

`requests` 已在用；签名用 hmac/hashlib/base64 均为 stdlib。

### 2.1 新文件 `zentray/services/feishu_bot.py`（~55 行）

```python
"""飞书群自定义机器人推送封装。"""
import base64
import hashlib
import hmac
import logging
import time
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class FeishuBotService:
    def __init__(self, webhook: str = "", secret: str = ""):
        self.webhook = (webhook or "").strip()
        self.secret = (secret or "").strip()

    def is_configured(self) -> bool:
        return self.webhook.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/")

    def _sign(self, timestamp: int) -> str:
        string_to_sign = f"{timestamp}\n{self.secret}"
        return base64.b64encode(
            hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        ).decode("utf-8")

    def send_message(self, content: str, summary: str = "ZenTray 通知") -> Dict[str, Any]:
        if not self.is_configured():
            return {"code": -1, "msg": "feishu bot webhook is missing."}
        # 请求体上限 20KB（UTF-8），超长截断而不是失败
        text = f"{summary}\n{content}"
        text = text.encode("utf-8")[:20000].decode("utf-8", errors="ignore")
        payload: Dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
        if self.secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = self._sign(ts)
        try:
            resp = requests.post(self.webhook, json=payload, timeout=10)
            data = resp.json()
            return data if isinstance(data, dict) else {"code": -1, "msg": f"unexpected: {data}"}
        except Exception as e:
            logger.warning("Feishu bot send failed: %s", e)
            return {"code": -1, "msg": str(e)}
```

注意：日志只打异常对象，**绝不打 webhook / secret**（等于凭证）。secret 留空 = 用户未开签名校验（关键词/无安全设置），正常裸发。

### 2.2 `zentray/services/settings_manager.py`（4 处小改）

1. `NotifyChannel` 加字段 `feishu_webhook: str = ""`、`feishu_secret: str = ""`；`__post_init__` 名称映射加 `"feishu_bot": "飞书机器人"`；`from_dict` 解析同名字段
2. `default_notify_channels()` 追加 `NotifyChannel(type="feishu_bot", name="飞书机器人", enabled=False)`（默认关，与 WxPusher 一致）
3. `sanitize_channel_types()` 白名单加 `"feishu_bot"`（一处函数，plan/review/ops 三处 notify_channels 全部经它清洗，自动生效）
4. `NotificationSettings` 加 `feishu_bot_channels()` 辅助方法；`SettingsManager.is_notification_configured()` 加 webhook 判断

`_sync_notif_legacy_to_channels()` 补一段「确保有 feishu_bot 渠道」，老 settings.json 升级后自动多出该卡（默认关），零迁移。

### 2.3 `zentray/services/notification.py`（~12 行）

`send()` 的 WxPusher 块之后追加：

```python
# 飞书群机器人（多条同理）
for ch in n.feishu_bot_channels() if (sel is None or "feishu_bot" in sel) else []:
    bot = FeishuBotService(webhook=ch.feishu_webhook, secret=ch.feishu_secret)
    if not bot.is_configured():
        results["channels"][ch.id or ch.name] = {"status": "error", "message": "未配置 Webhook"}
        continue
    r = bot.send_message(content=content, summary=title)
    results["channels"][ch.id or ch.name] = r
    if r.get("code") == 0:
        any_ok = True
```

### 2.4 `zentray/ui/controller.py`（1 处，`_on_ops_report`）

后台线程推送的渠道列表加成员（与 wecom_bot 设计同一处）：

```python
push_channels = [c for c in ("wxpusher", "feishu_bot") if not sel or c in sel]
```

（一次 `NotificationClient.send(channels=push_channels)` 调用覆盖多渠道，线程数不变。）

### 2.5 前端（3 个文件）

- **Settings.vue 通知页**：`ensureFixedChannels()` 固定追加 feishu_bot 卡（默认关）；渠道体按 `ch.type === 'feishu_bot'` 渲染 Webhook + 签名密钥两个输入框（`a-input`，placeholder 分别为 `https://open.feishu.cn/open-apis/bot/v2/hook/...` 与「签名密钥（未开启签名校验可留空）」，未启用时 disabled，样式复用 WxPusher 卡）
- **JobEditor.vue**（计划/复盘）与 **Settings.vue 插件页**：两处「完成通知渠道」checkbox-group 各加 `<a-checkbox value="feishu_bot">飞书机器人</a-checkbox>`；「空=跟随全局」物化为全选的两处数组补 `'feishu_bot'`
- 「至少保留一项」逻辑不变（兜底回落 app_popup 即可）

### 2.6 测试与文档

- `tests/` 补 `test_feishu_bot.py`：mock `requests.post` 断言 code 0→成功、非 0→失败、webhook 缺失→未配置、secret 有值时 body 含 timestamp/sign 且签名可复算；`sanitize_channel_types` 加 feishu_bot 白名单断言（若已有通知测试文件则并入）
- `docs/USER_MANUAL.md` 通知章节补渠道说明（含「需在飞书群内接收」「建议开启签名校验」提示）

改动量合计：1 个新文件 + 5 个文件小改，约 110 行。

## 3. 可行性评估：**高**

| 维度 | 评估 |
|------|------|
| 技术可行性 | ✅ 官方稳定 API（webhook 为飞书基础能力）；单一 POST，签名纯 stdlib（官方示例即 Python 标准库），无鉴权流程、无审批、无 SDK |
| 工程可行性 | ✅ 完全复刻 WxPusher 的既有模式（服务封装类→NotifyChannel→NotificationClient 分发→前端固定卡），无新模式引入；零新依赖 |
| 数据链路 | ✅ 点对点直连飞书官方 API，比 WxPusher（第三方中转）少一方信任暴露 |
| 失败隔离 | ✅ 单渠道异常被各自 try/except 吞掉记日志，不影响其他渠道（现有 send() 结构天然保证） |
| 成本 | ✅ 免费；个人飞书建群加机器人即可，无需企业管理员审核 |

## 4. 潜在风险

| # | 风险 | 等级 | 缓解 |
|---|------|------|------|
| 1 | **webhook 即凭证**：拿到 URL 的任何人都能向群里发消息 | 中 | 与 WxPusher token 同级对待——settings.json 本地明文存储（现状一致）；日志/输出绝不打 webhook/secret（现有凭证纪律沿用）；泄露后在群里移除机器人重加即重置；文档建议开启签名校验，secret 不随 URL 泄露即裸发无效 |
| 2 | **接收方需飞书 App 且在群内**：微信里收不到 | 中（期望管理） | 设置页与文档明示「需飞书群内接收」；想要微信推送的用户已有 WxPusher，多渠道互补而非替代 |
| 3 | 频控 100 条/分钟（限流码 11232，整点半点更易触发） | 低 | 本应用量级（每日计划/复盘 + 插件报告）远达不到；超限 code 非 0 记 warning，不做重试（重试放大风暴） |
| 4 | text 不渲染 markdown（AI 报告降级为纯文本） | 低 | 报告以文本为主，可读性损失小；未来可升级 interactive 卡片，YAGNI 暂不做 |
| 5 | 签名依赖本机时钟（偏差 >1 小时即 19021 失败） | 极低 | 个人电脑默认 NTP 同步；报错信息原样透传，用户可自查；secret 留空场景无此风险 |
| 6 | 备份导出含 webhook/secret | 低 | 现有备份 UI 已对含密钥项标红并二次确认，随 settings.json 走同一通道，无需新逻辑 |
| 7 | 飞书侧 API 变更/下线 | 极低 | webhook 是基础能力；即便失效也只是该渠道报错，弹窗/WxPusher 不受影响 |

**结论**：方案可行性高、风险可控且均有现成缓解路径；实现是 WxPusher 的结构性复制（多一个 stdlib 签名函数），预计半天内含测试完成。
