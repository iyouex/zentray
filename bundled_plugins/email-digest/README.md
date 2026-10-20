# 邮箱日报（email-digest）

读取多个邮箱账号自上次运行以来的新邮件，汇总为一份日报。IMAP **只读**操作
（LOGIN / AUTHENTICATE / SELECT readonly / UID FETCH BODY.PEEK / LOGOUT），
不置已读标志，不移动不删除邮件。仅用 Python 3 标准库，无第三方依赖。

## 配置账号

1. 把本目录 `config.example.json` 复制为**插件数据目录**下的 `config.json`：

   ```
   ~/.local/share/ZenTray/plugin_data/email-digest/config.json
   ```

   （即运行时注入的 `$ZENTRAY_PLUGIN_DATA_DIR`；写在数据目录是为了 zip 覆盖重装不丢。）

2. 结构：`{"accounts": [...], "ai_summary": false}`（旧版纯数组也兼容，
   等价于无 ai_summary 的 accounts）。账号字段：

   | 字段 | 说明 |
   |------|------|
   | `name` | 账号显示名（汇总中的小节名，如「个人」「公司」） |
   | `host` / `port` / `ssl` | IMAP 服务器、端口（SSL 通常 993）、`ssl: true` 走 IMAP4_SSL |
   | `user` | 登录用户名（通常为邮箱地址） |
   | `auth` | `"password"`（缺省）或 `"xoauth2"` |
   | `password` | `auth: password` 时的密码；QQ/163 等需用**授权码 / 应用专用密码** |
   | `oauth2` | `auth: xoauth2` 时的 OAuth2 配置（见下） |
   | `folders` | 要检查的文件夹列表，缺省 `["INBOX"]`，如 `["INBOX", "Archive"]` |

   `oauth2` 对象：

   | 字段 | 说明 |
   |------|------|
   | `provider` | `gmail` \| `microsoft` \| `custom` |
   | `client_id` | 应用的 client id |
   | `client_secret` | 可选；Gmail 桌面应用 / M365 公共客户端可省略 |
   | `refresh_token` | 离线刷新令牌（获取方法见下） |
   | `tenant` | provider 为 microsoft 时必填（`common` 或公司 tenant id） |
   | `token_url` / `scope` | provider 为 custom 时必填 / 可选（自建或其它提供商的令牌端点） |

   access_token 由 refresh_token 自动换取并缓存于 `state.json`（提前 5 分钟
   过期自动刷新），密钥与令牌不会写入任何日志/输出。

3. 顶层 `"ai_summary": true`（默认 false）：全部账号处理完后，把「发件人 ─ 主题」
   列表（**不含任何邮件凭证**）发给 ZenTray 已配置的 AI（OpenAI 兼容
   `/chat/completions`；配置优先级 环境变量 `AI_API_KEY` / `AI_API_BASE_URL` /
   `AI_MODEL_NAME` > `settings.json` 活跃 AI profile，与主程序一致），在汇总里
   追加一段「AI 摘要」。AI 调用失败只降级为「⚠ AI 摘要失败」，不影响整体结果。

`config.json` 缺失/非法/为空时运行会输出 `RESULT fail 配置缺失：…` 并以退出码 1
结束。**不要**把填好凭据的 config.json 提交或打包分享。

## 如何拿到 refresh_token

**Gmail**（scope `https://mail.google.com/`）：

1. [Google Cloud Console](https://console.cloud.google.com/) 建项目，启用
   「Gmail API」，配置 OAuth 同意屏（测试用户加自己）。
2. 创建 **桌面应用** OAuth 客户端，得 `client_id`（桌面应用可不设 secret）。
3. 用该 client 走授权码流程拿 `refresh_token`：最省事的是
   [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)
   （右上级齿轮 → Use your own client credentials 填入 client_id/secret，
   手动输入 scope `https://mail.google.com/` 授权），或 `gcloud auth print-tokens`
   / `rclone` 等工具。Gmail 账号还需保持 IMAP 开启（设置 → 转发和 POP/IMAP）。

**Microsoft 365 / Outlook**（scope
`https://outlook.office365.com/IMAP.AccessAsUser.All offline_access`）：

1. [Azure Portal](https://portal.azure.com/) → Microsoft Entra ID → 应用注册，
   得 `client_id`（`application (client) id`）与 `tenant`（公共客户端可用
   `common`；公司租户用 tenant id）。
2. 平台选「移动和桌面应用」→ 重定向 URI `http://localhost`；委托权限加
   `IMAP.AccessAsUser.All`（Microsoft Graph 下的 `offline_access` 默认就有；
   个人 outlook.com 用 `https://outlook.office365.com/IMAP.AccessAsUser.All`）。
3. 授权码流程换 `refresh_token`：浏览器开
   `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?client_id={cid}&response_type=code&redirect_uri=http://localhost&scope={scope空格分隔,URL编码}`，
   从跳转地址取出 `code=`，再 POST 到
   `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
   （`grant_type=authorization_code`）即得 refresh_token。

## 运行行为

- **触发**：随所关联任务的弹窗时刻自动运行（v0.7.15 起插件无自身调度；
  建一条周期任务并关联本插件即可定时跑）。
- **写回**：`write_back: true`——通过任务关联运行（任务表单选择本插件）时，
  RESULT 汇总文本会追加写回任务备注；任务已归档则写入当日归档日志。
- **新邮件判定**：状态文件 `$ZENTRAY_PLUGIN_DATA_DIR/state.json` 按账号×文件夹
  记录 `{uidvalidity, last_uid}`（键 `账号名|文件夹`；旧版无 `|` 的键自动迁移为
  `账号名|INBOX`）；正常运行取 UID 大于 `last_uid` 的邮件；首次运行（或服务器
  UIDVALIDITY 变化）回退取最近 24 小时内（按 Date 头）的邮件。
- **汇总格式**：每账号一节（账号名 + 新增 N 封，其下每封「时间 发件人 ─ 主题」，
  无新邮件写「无新邮件」），末行「共 X 封」；单账号超 50 封只列最新 50 封并注明。
  受 stdout 协议按行解析的限制，RESULT 为单行：账号节以「｜」、邮件行以「；」分隔。
- **容错**：单账号网络/认证/令牌失败不中断其它账号，计入汇总「失败」节；全部账号
  失败才以退出码 1 + `RESULT fail` 结束。密码、refresh_token、access_token
  不会出现在任何日志/输出中。

## 自测

```
./email_digest.py --selftest
```

用内置的假 IMAP 类与假令牌/chat 端点（canned 响应）跑通「令牌获取→认证→读取→
汇总→状态更新→RESULT 输出」全链路并断言（含 XOAUTH2 SASL 字节串、令牌缓存、
敏感串不泄露、多文件夹、旧 state 迁移、AI 摘要成败两路），不连任何真实邮箱。
