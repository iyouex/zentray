# zentray/services/settings_manager.py
"""
设置管理器 —— 统一管理应用配置的持久化与读取。

优先级：settings.json > .env 环境变量 > 代码默认值

v0.4 AI/通知模型：
  - 多 API Profile（命名，同时仅一个启用）
  - 每日计划 + 每日复盘（各自开关、调度、风格与可编辑提示词）
  - 多通知渠道（可同时开启：应用弹窗 / WxPusher）
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from zentray.config import DATA_DIR
from zentray.core.categories import CategorySettings, default_category_settings
from zentray.services.ai_styles import (
    AIStyle,
    STYLE_TOXIC,
    merge_styles,
    resolve_active_style,
)

SETTINGS_FILE = DATA_DIR / "settings.json"


@dataclass
class PollingSettings:
    high_priority_seconds: int = 4
    medium_priority_seconds: int = 2
    low_priority_seconds: int = 2
    rotation_mode: str = "random"
    enable_overdue_rotation: bool = True
    overdue_prefix: str = "【已逾期】"


@dataclass
class PomodoroSettings:
    duration_minutes: int = 25
    extend_minutes: int = 10
    # 托盘文字：countdown=倒计时 mm:ss；text=自定义文案（左侧始终为番茄饼图）
    tray_display: str = "countdown"  # countdown | text
    tray_text: str = "专注中"


@dataclass
class NightlySettings:
    """兼容旧版；新逻辑以 ai.review 为准，读写时双向同步。"""

    trigger_hour: int = 23
    trigger_minute: int = 30
    save_local: bool = True
    skip_weekends: bool = False
    skip_holidays: bool = False


@dataclass
class NotifyChannel:
    """通知渠道。type: app_popup | wxpusher"""

    id: str = ""
    type: str = "app_popup"  # app_popup | wxpusher
    name: str = ""
    enabled: bool = True
    wxpusher_app_token: str = ""
    wxpusher_uid: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.name:
            self.name = {
                "app_popup": "应用弹窗",
                "wxpusher": "WxPusher",
            }.get(self.type, self.type)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NotifyChannel":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            type=(data.get("type") or "app_popup").strip(),
            name=(data.get("name") or "").strip(),
            enabled=bool(data.get("enabled", True)),
            wxpusher_app_token=data.get("wxpusher_app_token") or "",
            wxpusher_uid=data.get("wxpusher_uid") or "",
        )


def default_notify_channels() -> List[NotifyChannel]:
    return [
        NotifyChannel(type="app_popup", name="应用弹窗", enabled=True),
        NotifyChannel(type="wxpusher", name="WxPusher", enabled=False),
    ]


@dataclass
class NotificationSettings:
    """多渠道通知；可同时开启。"""

    channels: List[NotifyChannel] = field(default_factory=default_notify_channels)
    # 兼容旧字段（读写时同步到 wxpusher 渠道）
    enabled: bool = True
    wxpusher_app_token: str = ""
    wxpusher_uid: str = ""

    def wxpusher_channels(self) -> List[NotifyChannel]:
        return [c for c in self.channels if c.type == "wxpusher" and c.enabled]

    def app_popup_enabled(self) -> bool:
        return any(c.type == "app_popup" and c.enabled for c in self.channels)

    def any_enabled(self) -> bool:
        return any(c.enabled for c in self.channels)


@dataclass
class QuickAddSettings:
    default_category: str = "工作"
    default_priority: str = "medium"


@dataclass
class AppearanceSettings:
    """系统/外观。theme: light | dark | system；autostart 为开机自启偏好；
    motion: full|off 界面动效开关；shape: round|crisp 形状风格；
    skin: neo|aurora 界面皮肤。"""

    theme: str = "system"
    autostart: bool = False
    motion: str = "full"
    shape: str = "round"
    skin: str = "neo"


@dataclass
class AIApiProfile:
    """命名模型接入配置；同时仅 active_api_id 对应的一个生效。"""

    id: str = ""
    name: str = "默认"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not (self.name or "").strip():
            self.name = "未命名"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AIApiProfile":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            name=(data.get("name") or "未命名").strip() or "未命名",
            api_key=data.get("api_key") or "",
            base_url=(data.get("base_url") or "https://api.openai.com/v1").strip(),
            model=(data.get("model") or "gpt-4o").strip() or "gpt-4o",
        )


@dataclass
class AIJobSettings:
    """每日计划 / 每日复盘 共用结构。"""

    enabled: bool = True
    trigger_hour: int = 8
    trigger_minute: int = 0
    active_style_id: str = STYLE_TOXIC
    styles: List[AIStyle] = field(default_factory=list)
    skip_weekends: bool = False
    skip_holidays: bool = False
    save_local: bool = True

    def __post_init__(self):
        # styles 由外部 merge 注入；此处仅保证列表
        if self.styles is None:
            self.styles = []

    def active_style(self) -> AIStyle:
        return resolve_active_style(self.styles, self.active_style_id)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "trigger_hour": int(self.trigger_hour),
            "trigger_minute": int(self.trigger_minute),
            "active_style_id": self.active_style_id,
            "styles": [s.to_dict() for s in self.styles],
            "skip_weekends": self.skip_weekends,
            "skip_holidays": self.skip_holidays,
            "save_local": self.save_local,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict], *, kind: str) -> "AIJobSettings":
        data = data or {}
        styles = merge_styles(data.get("styles"), kind=kind)
        return cls(
            enabled=bool(data.get("enabled", True)),
            trigger_hour=int(data.get("trigger_hour", 8 if kind == "plan" else 23)),
            trigger_minute=int(data.get("trigger_minute", 0 if kind == "plan" else 30)),
            active_style_id=data.get("active_style_id") or STYLE_TOXIC,
            styles=styles,
            skip_weekends=bool(data.get("skip_weekends", False)),
            skip_holidays=bool(data.get("skip_holidays", False)),
            save_local=bool(data.get("save_local", True)),
        )


@dataclass
class AIFeatureSettings:
    """AI 场景能力开关（智能解析/图片识别/任务建议），默认全关。"""

    smart_parse: bool = False
    image_ocr: bool = False
    task_suggest: bool = False

    def to_dict(self) -> dict:
        return {
            "smart_parse": bool(self.smart_parse),
            "image_ocr": bool(self.image_ocr),
            "task_suggest": bool(self.task_suggest),
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AIFeatureSettings":
        data = data or {}
        return cls(
            smart_parse=bool(data.get("smart_parse", False)),
            image_ocr=bool(data.get("image_ocr", False)),
            task_suggest=bool(data.get("task_suggest", False)),
        )


@dataclass
class AISettings:
    """
    AI 总配置：
      - api_profiles + active_api_id：多 Key，单启用
      - plan / review：每日计划与每日复盘
      - features：场景化 AI 能力开关（docs/AI-FEATURES.md）
    旧字段 api_key/base_url/model/enabled/styles 在迁移时并入。
    """

    api_profiles: List[AIApiProfile] = field(default_factory=list)
    active_api_id: str = ""
    plan: AIJobSettings = field(default_factory=lambda: AIJobSettings.from_dict(None, kind="plan"))
    features: AIFeatureSettings = field(default_factory=AIFeatureSettings)
    review: AIJobSettings = field(
        default_factory=lambda: AIJobSettings.from_dict(
            {"trigger_hour": 23, "trigger_minute": 30}, kind="review"
        )
    )
    # —— 兼容旧字段（属性访问）——
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    active_style_id: str = STYLE_TOXIC
    styles: List[AIStyle] = field(default_factory=list)

    def __post_init__(self):
        if not self.api_profiles:
            # 从兼容字段建默认 profile
            pid = str(uuid.uuid4())
            self.api_profiles = [
                AIApiProfile(
                    id=pid,
                    name="默认",
                    api_key=self.api_key or "",
                    base_url=self.base_url or "https://api.openai.com/v1",
                    model=self.model or "gpt-4o",
                )
            ]
            self.active_api_id = pid
        if not self.active_api_id and self.api_profiles:
            self.active_api_id = self.api_profiles[0].id
        # 同步兼容字段
        self._sync_legacy_from_active()
        # review styles 同步到 legacy styles
        if self.review and self.review.styles:
            self.styles = self.review.styles
            self.active_style_id = self.review.active_style_id
            self.enabled = self.review.enabled or self.plan.enabled

    def _sync_legacy_from_active(self) -> None:
        p = self.active_profile()
        if p:
            self.api_key = p.api_key
            self.base_url = p.base_url
            self.model = p.model

    def active_profile(self) -> Optional[AIApiProfile]:
        for p in self.api_profiles:
            if p.id == self.active_api_id:
                return p
        return self.api_profiles[0] if self.api_profiles else None

    def active_style(self) -> AIStyle:
        """默认用复盘风格（兼容旧调用）。"""
        return self.review.active_style()

    def to_dict(self) -> dict:
        self._sync_legacy_from_active()
        return {
            "api_profiles": [p.to_dict() for p in self.api_profiles],
            "active_api_id": self.active_api_id,
            "plan": self.plan.to_dict(),
            "review": self.review.to_dict(),
            "features": self.features.to_dict(),
            # 兼容旧客户端
            "enabled": bool(self.plan.enabled or self.review.enabled),
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "active_style_id": self.review.active_style_id,
            "styles": [s.to_dict() for s in self.review.styles],
        }


@dataclass
class AppSettings:
    polling: PollingSettings = field(default_factory=PollingSettings)
    pomodoro: PomodoroSettings = field(default_factory=PomodoroSettings)
    nightly: NightlySettings = field(default_factory=NightlySettings)
    notification: NotificationSettings = field(default_factory=NotificationSettings)
    ai: AISettings = field(default_factory=AISettings)
    categories: CategorySettings = field(default_factory=default_category_settings)
    quick_add: QuickAddSettings = field(default_factory=QuickAddSettings)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)


class SettingsManager:
    """应用设置管理器（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._settings = AppSettings()
        self._load_from_env()
        self._load_from_file()
        self._loaded = True

    def _load_from_env(self) -> None:
        notif = self._settings.notification
        if os.getenv("WXPUSHER_APP_TOKEN"):
            notif.wxpusher_app_token = os.getenv("WXPUSHER_APP_TOKEN")
        if os.getenv("WXPUSHER_UID"):
            notif.wxpusher_uid = os.getenv("WXPUSHER_UID")
        # 同步到渠道
        self._sync_notif_legacy_to_channels()

        ai = self._settings.ai
        key = os.getenv("AI_API_KEY")
        if key:
            p = ai.active_profile()
            if p:
                p.api_key = key
            ai.api_key = key
        base = os.getenv("AI_API_BASE_URL")
        if base:
            p = ai.active_profile()
            if p:
                p.base_url = base
            ai.base_url = base
        model = os.getenv("AI_MODEL_NAME")
        if model:
            p = ai.active_profile()
            if p:
                p.model = model
            ai.model = model
        ai._sync_legacy_from_active()

    def _sync_notif_legacy_to_channels(self) -> None:
        n = self._settings.notification
        if not n.channels:
            n.channels = default_notify_channels()
        # 找到/创建 wxpusher 渠道
        wx = next((c for c in n.channels if c.type == "wxpusher"), None)
        if wx is None:
            wx = NotifyChannel(type="wxpusher", name="WxPusher", enabled=False)
            n.channels.append(wx)
        if n.wxpusher_app_token:
            wx.wxpusher_app_token = n.wxpusher_app_token
        if n.wxpusher_uid:
            wx.wxpusher_uid = n.wxpusher_uid
        if n.wxpusher_app_token and n.wxpusher_uid and n.enabled:
            wx.enabled = True
        # 确保有 app_popup
        if not any(c.type == "app_popup" for c in n.channels):
            n.channels.insert(
                0, NotifyChannel(type="app_popup", name="应用弹窗", enabled=True)
            )

    def _sync_notif_channels_to_legacy(self) -> None:
        n = self._settings.notification
        wx = next((c for c in n.channels if c.type == "wxpusher"), None)
        if wx:
            n.wxpusher_app_token = wx.wxpusher_app_token
            n.wxpusher_uid = wx.wxpusher_uid
            n.enabled = n.any_enabled()
        else:
            n.enabled = n.any_enabled()

    def reload(self) -> None:
        """从磁盘重新加载 settings（导入备份后调用）。"""
        self._settings = AppSettings()
        self._load_from_env()
        self._load_from_file()
        self._loaded = True

    def _load_from_file(self) -> None:
        if not SETTINGS_FILE.exists():
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_dict(data)
        except (json.JSONDecodeError, Exception):
            pass

    def _apply_dict(self, data: dict) -> None:
        if "polling" in data:
            p = data["polling"]
            self._settings.polling = PollingSettings(
                high_priority_seconds=p.get("high_priority_seconds", 4),
                medium_priority_seconds=p.get("medium_priority_seconds", 2),
                low_priority_seconds=p.get("low_priority_seconds", 2),
                rotation_mode=p.get("rotation_mode", "random"),
                enable_overdue_rotation=p.get("enable_overdue_rotation", True),
                overdue_prefix=p.get("overdue_prefix", "【已逾期】"),
            )
        if "pomodoro" in data:
            p = data["pomodoro"]
            disp = (p.get("tray_display") or "countdown").lower()
            if disp not in ("countdown", "text"):
                disp = "countdown"
            self._settings.pomodoro = PomodoroSettings(
                duration_minutes=p.get("duration_minutes", 25),
                extend_minutes=p.get("extend_minutes", 10),
                tray_display=disp,
                tray_text=(p.get("tray_text") or "专注中").strip() or "专注中",
            )
        if "nightly" in data:
            n = data["nightly"]
            self._settings.nightly = NightlySettings(
                trigger_hour=n.get("trigger_hour", 23),
                trigger_minute=n.get("trigger_minute", 30),
                save_local=n.get("save_local", True),
                skip_weekends=bool(n.get("skip_weekends", False)),
                skip_holidays=bool(n.get("skip_holidays", False)),
            )
        if "notification" in data:
            n = data["notification"]
            channels_raw = n.get("channels")
            if channels_raw:
                channels = [
                    NotifyChannel.from_dict(c)
                    for c in channels_raw
                    if isinstance(c, dict)
                ]
            else:
                channels = default_notify_channels()
            self._settings.notification = NotificationSettings(
                channels=channels,
                enabled=n.get("enabled", True),
                wxpusher_app_token=n.get("wxpusher_app_token", ""),
                wxpusher_uid=n.get("wxpusher_uid", ""),
            )
            self._sync_notif_legacy_to_channels()

        if "ai" in data:
            self._settings.ai = self._parse_ai(data["ai"], nightly=self._settings.nightly)

        # 若仅有 nightly 而无 ai.review 新字段，已在 _parse_ai 处理
        if "categories" in data:
            self._settings.categories = CategorySettings.from_dict(data["categories"])
        if "quick_add" in data:
            q = data["quick_add"]
            self._settings.quick_add = QuickAddSettings(
                default_category=q.get("default_category", "工作"),
                default_priority=q.get("default_priority", "medium"),
            )
        if "appearance" in data:
            a = data["appearance"] or {}
            theme = str(a.get("theme") or "system").lower()
            if theme not in ("light", "dark", "system"):
                theme = "system"
            autostart = bool(a.get("autostart", False))
            motion = str(a.get("motion") or "full").lower()
            if motion not in ("full", "off"):
                motion = "full"
            shape = str(a.get("shape") or "round").lower()
            if shape not in ("round", "crisp"):
                shape = "round"
            skin = str(a.get("skin") or "neo").lower()
            if skin not in ("neo", "aurora"):
                skin = "neo"
            self._settings.appearance = AppearanceSettings(
                theme=theme,
                autostart=autostart,
                motion=motion,
                shape=shape,
                skin=skin,
            )

        # 用 review 回写 nightly 兼容
        self._sync_nightly_from_review()

    def _parse_ai(self, a: dict, nightly: Optional[NightlySettings] = None) -> AISettings:
        nightly = nightly or NightlySettings()
        # profiles
        profiles_raw = a.get("api_profiles") or []
        profiles: List[AIApiProfile] = []
        for raw in profiles_raw:
            if isinstance(raw, dict):
                profiles.append(AIApiProfile.from_dict(raw))
        if not profiles:
            # 旧版单 key
            profiles = [
                AIApiProfile(
                    name="默认",
                    api_key=a.get("api_key") or "",
                    base_url=a.get("base_url") or "https://api.openai.com/v1",
                    model=a.get("model") or "gpt-4o",
                )
            ]
        active_api_id = a.get("active_api_id") or profiles[0].id

        # plan / review
        if "plan" in a or "review" in a:
            plan = AIJobSettings.from_dict(a.get("plan"), kind="plan")
            review = AIJobSettings.from_dict(a.get("review"), kind="review")
        else:
            # 旧版：单一 AI + nightly 时间 → 复盘；计划默认早 8 点关闭或开启
            old_styles = a.get("styles")
            review = AIJobSettings.from_dict(
                {
                    "enabled": a.get("enabled", True),
                    "trigger_hour": nightly.trigger_hour,
                    "trigger_minute": nightly.trigger_minute,
                    "active_style_id": a.get("active_style_id", STYLE_TOXIC),
                    "styles": old_styles,
                    "skip_weekends": nightly.skip_weekends,
                    "skip_holidays": nightly.skip_holidays,
                    "save_local": nightly.save_local,
                },
                kind="review",
            )
            plan = AIJobSettings.from_dict(
                {
                    "enabled": False,
                    "trigger_hour": 8,
                    "trigger_minute": 0,
                    "active_style_id": STYLE_TOXIC,
                    "styles": None,
                },
                kind="plan",
            )

        return AISettings(
            api_profiles=profiles,
            active_api_id=active_api_id,
            plan=plan,
            review=review,
            features=AIFeatureSettings.from_dict(a.get("features")),
            enabled=bool(plan.enabled or review.enabled),
            api_key=a.get("api_key") or "",
            base_url=a.get("base_url") or "https://api.openai.com/v1",
            model=a.get("model") or "gpt-4o",
            active_style_id=review.active_style_id,
            styles=review.styles,
        )

    def _sync_nightly_from_review(self) -> None:
        r = self._settings.ai.review
        self._settings.nightly = NightlySettings(
            trigger_hour=r.trigger_hour,
            trigger_minute=r.trigger_minute,
            save_local=r.save_local,
            skip_weekends=r.skip_weekends,
            skip_holidays=r.skip_holidays,
        )

    def save(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        self._sync_notif_channels_to_legacy()
        self._sync_nightly_from_review()
        self._settings.ai._sync_legacy_from_active()
        data = {
            "polling": asdict(self._settings.polling),
            "pomodoro": asdict(self._settings.pomodoro),
            "nightly": asdict(self._settings.nightly),
            "notification": {
                "channels": [c.to_dict() for c in self._settings.notification.channels],
                "enabled": self._settings.notification.enabled,
                "wxpusher_app_token": self._settings.notification.wxpusher_app_token,
                "wxpusher_uid": self._settings.notification.wxpusher_uid,
            },
            "ai": self._settings.ai.to_dict(),
            "categories": self._settings.categories.to_dict(),
            "quick_add": asdict(self._settings.quick_add),
            "appearance": asdict(self._settings.appearance),
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @property
    def polling(self) -> PollingSettings:
        return self._settings.polling

    @property
    def pomodoro(self) -> PomodoroSettings:
        return self._settings.pomodoro

    @property
    def nightly(self) -> NightlySettings:
        return self._settings.nightly

    @property
    def notification(self) -> NotificationSettings:
        return self._settings.notification

    @property
    def ai(self) -> AISettings:
        return self._settings.ai

    @property
    def categories(self) -> CategorySettings:
        return self._settings.categories

    @property
    def quick_add(self) -> QuickAddSettings:
        return self._settings.quick_add

    @property
    def appearance(self) -> AppearanceSettings:
        return self._settings.appearance

    def get_all(self) -> AppSettings:
        return self._settings

    def get_dwell_seconds(self, priority: str) -> int:
        mapping = {
            "high": self.polling.high_priority_seconds,
            "medium": self.polling.medium_priority_seconds,
            "low": self.polling.low_priority_seconds,
        }
        return mapping.get(priority, 2)

    def is_notification_configured(self) -> bool:
        """任一可用渠道已配置即视为可通知。"""
        n = self.notification
        if n.app_popup_enabled():
            return True
        for c in n.wxpusher_channels():
            if c.wxpusher_app_token and c.wxpusher_uid:
                return True
        # 旧字段
        return bool(n.enabled and n.wxpusher_app_token and n.wxpusher_uid)

    def is_ai_configured(self) -> bool:
        p = self.ai.active_profile()
        if not p or not p.api_key:
            return False
        return bool(self.ai.plan.enabled or self.ai.review.enabled)

    @classmethod
    def reload(cls) -> "SettingsManager":
        cls._instance = None
        return cls()
