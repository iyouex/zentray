"""飞书群自定义机器人推送封装（webhook + 可选签名校验）。"""
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
        # 官方算法：key = "timestamp\nsecret"，被签消息为空串
        string_to_sign = f"{timestamp}\n{self.secret}"
        return base64.b64encode(
            hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        ).decode("utf-8")

    def send_message(self, content: str, summary: str = "ZenTray 通知") -> Dict[str, Any]:
        if not self.is_configured():
            return {"code": -1, "msg": "feishu bot webhook is missing."}
        # 请求体上限 20KB：超长截断而不是失败
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
            # 逻辑错误也返 200，必须查 code
            return data if isinstance(data, dict) else {"code": -1, "msg": str(data)}
        except Exception as e:
            # 日志绝不打 webhook / secret（等于凭证）
            logger.warning("Feishu bot send failed: %s", e)
            return {"code": -1, "msg": str(e)}
