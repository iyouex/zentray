# 微信机器人通知渠道 —— 设计方案与可行性评估

> 状态：设计稿，未实现。目标：在现有 app_popup / WxPusher 之外新增第三条通知渠道。

## 1. 选型：企业微信群机器人（WeCom Group Bot Webhook）

「微信机器人」有四条常见路线，选第一条：

| 路线 | 结论 |
|------|------|
| **企业微信群机器人 webhook** | ✅ 采用。官方 API、免企业认证（个人免费建团队即可）、单一凭证（webhook key）、一个 HTTP POST 完事 |
| 个人微信号机器人（itchat/wechaty/padlocal） | ❌ 违反微信服务条款，封号风险真实存在；依赖非官方协议库且重；拒绝 |
| 公众号模板消息 | ❌ 需认证服务号 + 模板审批 + 用户关注，为个人 GTD 工具做这些属于过度工程 |
| Server酱 / PushPlus | ❌ 本质是另一个 WxPusher 式中间商，与现有渠道同质，无增量价值 |

### API 要点（官方 webhook）

- 端点：`POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<KEY>`（key 即全部凭证）
- 报文：`{"msgtype":"markdown","markdown":{"content":"**标题**\n正文"}}`
  - markdown 上限 **4096 字节**（UTF-8）；text 型 2048，不采用
  - WeCom markdown 是子集（无表格、有限标签），AI 报告是普通 md 文本，降级显示可接受
- 成功返回 HTTP 200 + `{"errcode":0,"errmsg":"ok"}`；**逻辑错误也返回 200**，必须检查 errcode
- 频控：**每机器人 20 条/分钟**，超出返回错误码
- 机器人只能加在**企业微信内部群**，不能加在微信互通群 → 接收方需装企业微信 App（免费）

## 2. 实现方案（镜像 WxPusher，全程零新依赖）

主应用已用 `requests`（wxpusher.py:53），新渠道同样用。

### 2.1 新文件 `zentray/services/wecom_bot.py`（~40 行）

```python
"""企业微信群机器人推送封装。"""
import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class WeComBotService:
    def __init__(self, webhook: str = ""):
        self.webhook = (webhook or "").strip()

    def is_configured(self) -> bool:
        return self.webhook.startswith("https://") and "key=" in self.webhook

    def send_message(self, content: str, summary: str = "ZenTray 通知") -> Dict[str, Any]:
        if not self.is_configured():
            return {"errcode": -1, "errmsg": "wecom bot webhook is missing."}
        # 4096 字节是 content 字段上限（UTF-8），超长截断而不是失败
        text = f"**{summary}**\n{content}"
        text = text.encode("utf-8")[:4000].decode("utf-8", errors="ignore")
        try:
            resp = requests.post(
                self.webhook,
                json={"msgtype": "markdown", "markdown": {"content": text}},
                timeout=10,
            )
            data = resp.json()
            return data if isinstance(data, dict) else {"errcode": -1, "errmsg": f"unexpected: {data}"}
        except Exception as e:
            logger.warning("WeCom bot send failed: %s", e)
            return {"errcode": -1, "errmsg": str(e)}
```

注意：日志只打异常对象，**绝不打 webhook**（含 key，等于凭证）。

### 2.2 `zentray/services/settings_manager.py`（4 处小改）

1. `NotifyChannel` 加字段 `wecom_webhook: str = ""`；`__post_init__` 名称映射加 `"wecom_bot": "企业微信机器人"`；`from_dict` 解析同名字段
2. `default_notify_channels()` 追加 `NotifyChannel(type="wecom_bot", name="企业微信机器人", enabled=False)`（默认关，与 WxPusher 一致）
3. `sanitize_channel_types()` 白名单加 `"wecom_bot"`（一处函数，plan/review/ops 三处 notify_channels 全部经它清洗，自动生效）
4. `NotificationSettings` 加 `wecom_bot_channels()` 辅助方法；`SettingsManager.is_notification_configured()` 加 webhook 判断

`_sync_notif_legacy_to_channels()` 补一段「确保有 wecom_bot 渠道」，老 settings.json 升级后自动多出该卡（默认关），零迁移。

### 2.3 `zentray/services/notification.py`（~12 行）

`send()` 的 WxPusher 块之后追加：

```python
# 企业微信机器人（多条同理）
for ch in n.wecom_bot_channels() if (sel is None or "wecom_bot" in sel) else []:
    bot = WeComBotService(webhook=ch.wecom_webhook)
    if not bot.is_configured():
        results["channels"][ch.id or ch.name] = {"status": "error", "message": "未配置 Webhook"}
        continue
    r = bot.send_message(content=content, summary=title)
    results["channels"][ch.id or ch.name] = r
    if r.get("errcode") == 0:
        any_ok = True
```

### 2.4 `zentray/ui/controller.py`（1 处，`_on_ops_report`）

现后台线程硬编码 `channels=["wxpusher"]`。改为按选择构造：

```python
push_channels = [c for c in ("wxpusher", "wecom_bot") if not sel or c in c_sel]
```

（原来两个 `if not sel or ... in sel` 分支合一，`NotificationClient.send(channels=push_channels)` 一次调用覆盖两渠道，线程数不变。）

### 2.5 前端（3 个文件）

- **Settings.vue 通知页**：`ensureFixedChannels()` 固定追加 wecom_bot 第三卡（默认关）；渠道体加 webhook 输入框（`a-input`，placeholder `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...`，未启用时 disabled，样式复用 WxPusher 卡）
- **JobEditor.vue**（计划/复盘）与 **Settings.vue 插件页**：两处「完成通知渠道」checkbox-group 各加 `<a-checkbox value="wecom_bot">企业微信机器人</a-checkbox>`；「空=跟随全局」物化为全选的两处数组补 `'wecom_bot'`
- 「至少保留一项」逻辑不变（兜底回落 app_popup 即可）

### 2.6 测试与文档

- `tests/` 补一个 `test_wecom_bot.py`：mock `requests.post` 断言 errcode 0→成功、非 0→失败、webhook 缺失→未配置；`sanitize_channel_types` 加 wecom_bot 白名单断言（若已有通知测试文件则并入）
- `docs/USER_MANUAL.md` 通知章节补第三渠道说明（含「需企业微信 App 接收」提示）

改动量合计：1 个新文件 + 5 个文件小改，约 100 行。

## 3. 可行性评估：**高**

| 维度 | 评估 |
|------|------|
| 技术可行性 | ✅ 官方稳定 API（webhook 为企业微信基础能力，多年未变）；单一 POST，无鉴权流程、无审批、无 SDK |
| 工程可行性 | ✅ 完全复刻 WxPusher 的既有模式（服务封装类→NotifyChannel→NotificationClient 分发→前端固定卡），无新模式引入；零新依赖 |
| 数据链路 | ✅ 点对点直连腾讯官方 API，比 WxPusher（第三方中转）少一方信任暴露 |
| 失败隔离 | ✅ 单渠道异常被各自 try/except 吞掉记日志，不影响其他渠道（现有 send() 结构天然保证） |
| 成本 | ✅ 免费；个人注册企业微信建群加机器人即可，无需企业认证 |

## 4. 潜在风险

| # | 风险 | 等级 | 缓解 |
|---|------|------|------|
| 1 | **webhook key 即凭证**：拿到 URL 的任何人都能向群里发消息 | 中 | 与 WxPusher token 同级对待——settings.json 本地明文存储（现状一致）；日志/输出绝不打 webhook（现有凭证纪律沿用）；泄露后在群里移除机器人重加即可重置 key |
| 2 | **接收方需装企业微信 App**：机器人加不进微信互通群，个人微信里收不到 | 中（期望管理） | 设置页与文档明示「需企业微信接收」；想要微信正文推送的用户已有 WxPusher，两渠道互补而非替代 |
| 3 | 频控 20 条/分钟 | 低 | 本应用量级（每日计划/复盘 + 插件报告）远达不到；超限返回 errcode 记 warning，不做重试（懒：重试放大风暴） |
| 4 | md 渲染降级（WeCom md 子集，无表格） | 低 | 报告以文本为主，可读性损失小；不做 md→wecom-md 转换，YAGNI |
| 5 | 备份导出含 webhook | 低 | 现有备份 UI 已对含密钥项标红并二次确认，wecom_webhook 随 settings.json 走同一通道，无需新逻辑 |
| 6 | 腾讯侧 API 变更/下线 | 极低 | webhook 是基础能力；即便失效也只是该渠道报错，弹窗/WxPusher 不受影响 |

**结论**：方案可行性高、风险可控且均有现成缓解路径；实现是 WxPusher 的结构性复制，预计半天内含测试完成。
