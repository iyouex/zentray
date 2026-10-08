# ZenTray × 移动端 IM 联动方案（2026-10-08）

> 目标：飞书、企业微信及其他移动端通讯软件与 ZenTray 联动。
> 前提：通知出口已多渠道化（`NotificationClient.send` 单一漏斗 + `NotifyChannel` 渠道模型 + 每事件渠道白名单），本方案是**沿既有模式扩渠道**，不引入新框架。

## 0. 现状与地基

已有（未合并）：`feature/feishu-notify` @ 52b10a1 —— 飞书群机器人（webhook + 可选 HMAC 签名）、设置页固定卡、计划/复盘/插件通知渠道可选、109 行单测。
已有（在 v0.7.3）：渠道多选门控（`notify-channel-select`，每事件可选渠道类型子集）、WxPusher 多条渠道。

加一个渠道的固定动作（约 6 处，每处都很小）：

1. `NotifyChannel` 加凭证字段（`from_dict`/`to_dict` 自动跟随 asdict）
2. `default_notify_channels()` 默认项 + 类型名映射
3. `sanitize_channel_types` 白名单 + `NotificationSettings.xxx_channels()` 过滤器
4. 服务类（`feishu_bot.py` 同款：`is_configured` + `send_message(content, summary)`，日志不打凭证）
5. `NotificationClient.send` 加一个循环块
6. `Settings.vue` 固定卡 + 测试发送按钮

## 1. P0：单向推送扩渠道（建议第一批，约 2 天）

全部是「webhook POST JSON」同构渠道，零公网、零新依赖（requests 已有）：

| 渠道 | 凭证 | 端点校验 | 载荷/签名 | 备注 |
|---|---|---|---|---|
| 企业微信群机器人 | webhook 一条 | `qyapi.weixin.qq.com/cgi-bin/webhook/send` | `{"msgtype":"text","text":{"content":...}}`，无需签名 | 与飞书机器人完全同构，最省 |
| Telegram Bot | `bot_token` + `chat_id` | `api.telegram.org/bot<token>/sendMessage` | `chat_id` + `text` | **CN 网络需代理**：base_url 可改（自建 api 反代字段 `tg_api_base`，默认官方） |
| 钉钉群机器人 | webhook + secret | `oapi.dingtalk.com/robot/send` | 签名算法与飞书不同（key=secret, msg=`timestamp\n`） | 可选，第 4 个同构渠道顺手加 |

复用要点：
- 4 个服务类共享一个模块级 `_post_json(url, payload, timeout=10)`（requests + try/except + 不打凭证的 warning 日志），各自只写 payload 构造与签名——不建渠道插件框架，渠道数 <6 不值得（`# ponytail: 超 6 渠道再抽注册表`）。
- 类型白名单字符串在 sanitize/name-map 两处重复——收敛为一个 `CHANNEL_TYPES` 常量，新增渠道只改一处。
- **步骤 0：先把 `feature/feishu-notify` rebase 到当前 staging（5f8c39d）合入**——它是本批的地基，且停在 0.7.3 之前越久冲突越大（Settings.vue/handlers 均有 churn）。

明确不做（WxPusher 已覆盖微信个人生态）：Server酱、PushPlus、邮件、短信。

## 2. P1：双向联动（IM 里收发，独立决策后再开工）

单向推送到手机后，自然的下一步是在 IM 里**回一句加任务/查今日**。三条路线按可行性排序：

| 路线 | 收消息机制 | 公网要求 | 工作量 | 建议 |
|---|---|---|---|---|
| 飞书自建应用 + **长连接模式** | lark-oapi SDK WebSocket（事件订阅） | **无**（出站连接） | 3-4 天 | ✅ 首选：用户主用飞书，且免公网 |
| Telegram getUpdates | long-poll 轮询 | 无，但需代理 | 2-3 天 | 备选，网络是硬伤 |
| 企微智能机器人 | 回调 URL 验证 | **需公网 + 内网穿透** | 3 天 + 运维负担 | ❌ 单机 NAT 场景不建议 |

飞书长连接形态（若立项）：
- 新 `ImGatewayWorker`（QThread，与 watcher/nightly/reminder/plugin_trigger 同构，启停挂 `apply_settings`）
- 事件 → 解析文本指令（`加任务 xxx 3m` / `今日` / `完成 #3`）→ 直调 `TaskService`（注意 P1 前先落 D4 的 RLock——复盘已定性跨线程无锁是真实风险）
- 回消息走同一长连接；指令解析放纯函数可单测
- 凭证进 `NotifyChannel` 新字段（app_id/app_secret），不另起配置面

## 3. 实施顺序建议

1. **合入 `feature/feishu-notify`**（rebase → staging 验证 → 并入下个 PATCH）
2. P0 三渠道（企微 → Telegram → 钉钉），每个渠道一批 `test_*.py`（伪造 webhook 断言 payload/签名，同 `test_feishu_bot.py` 模式）
3. 判级：纯渠道扩展走 **PATCH**；若同批带 P1 飞书长连接双向，升 **MINOR**（0.8.0 已定留给瘦身，勿占用——双向联动应等瘦身落地后做 0.9.0 或插队另议）
