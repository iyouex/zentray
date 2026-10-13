"""飞书机器人通知渠道单测：签名、分发、白名单。"""
import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from zentray.services.feishu_bot import FeishuBotService
from zentray.services.settings_manager import (
    NotifyChannel,
    NotificationSettings,
    sanitize_channel_types,
)

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"


def _resp(data):
    m = MagicMock()
    m.json.return_value = data
    return m


def test_send_ok():
    bot = FeishuBotService(webhook=WEBHOOK)
    assert bot.is_configured()
    with patch("zentray.services.feishu_bot.requests.post", return_value=_resp({"code": 0, "msg": "success"})) as p:
        r = bot.send_message(content="正文", summary="标题")
    assert r["code"] == 0
    body = p.call_args.kwargs["json"]
    assert body["msg_type"] == "text"
    assert body["content"]["text"] == "标题\n正文"
    assert "timestamp" not in body and "sign" not in body


def test_send_logical_error_still_checked():
    """飞书逻辑错误也返 200，必须查 code。"""
    bot = FeishuBotService(webhook=WEBHOOK)
    with patch("zentray.services.feishu_bot.requests.post", return_value=_resp({"code": 19021, "msg": "sign match fail"})):
        r = bot.send_message(content="x")
    assert r["code"] == 19021


def test_missing_webhook_unconfigured():
    bot = FeishuBotService(webhook="", secret="s")
    assert not bot.is_configured()
    assert bot.send_message(content="x")["code"] == -1


def test_signed_payload_signature_recomputable():
    bot = FeishuBotService(webhook=WEBHOOK, secret="sec123")
    with patch("zentray.services.feishu_bot.requests.post", return_value=_resp({"code": 0})) as p:
        bot.send_message(content="x")
    body = p.call_args.kwargs["json"]
    ts = body["timestamp"]
    expect = base64.b64encode(
        hmac.new(f"{ts}\nsec123".encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    assert body["sign"] == expect


def test_sanitize_whitelist_includes_feishu():
    assert sanitize_channel_types(["app_popup", "feishu_bot", "bogus"]) == ["app_popup", "feishu_bot"]


def test_notification_settings_feishu_channels():
    n = NotificationSettings(
        channels=[
            NotifyChannel(type="feishu_bot", enabled=True, feishu_webhook=WEBHOOK),
            NotifyChannel(type="feishu_bot", enabled=False, feishu_webhook=WEBHOOK),
        ]
    )
    chs = n.feishu_bot_channels()
    assert len(chs) == 1 and chs[0].name == "飞书机器人"


def test_notification_client_dispatch_feishu():
    from zentray.services.notification import NotificationClient

    n = NotificationSettings(
        channels=[
            NotifyChannel(type="app_popup", enabled=False),
            NotifyChannel(type="feishu_bot", enabled=True, feishu_webhook=WEBHOOK),
        ]
    )
    with patch("zentray.services.settings_manager.SettingsManager") as sm, patch(
        "zentray.services.feishu_bot.requests.post", return_value=_resp({"code": 0})
    ) as p:
        sm.return_value.notification = n
        r = NotificationClient.from_settings().send("标题", "正文")
    assert r["status"] == "ok"
    assert p.called
    # 渠道结果键 = 渠道 id
    keys = list(r["channels"].keys())
    assert len(keys) == 1  # 仅 feishu（app_popup 关）


def test_notification_client_feishu_filtered_out():
    from zentray.services.notification import NotificationClient

    n = NotificationSettings(
        channels=[NotifyChannel(type="feishu_bot", enabled=True, feishu_webhook=WEBHOOK)]
    )
    with patch("zentray.services.settings_manager.SettingsManager") as sm, patch(
        "zentray.services.feishu_bot.requests.post"
    ) as p:
        sm.return_value.notification = n
        r = NotificationClient.from_settings().send("t", "c", channels=["wxpusher"])
    assert not p.called
    assert r["status"] == "error"
