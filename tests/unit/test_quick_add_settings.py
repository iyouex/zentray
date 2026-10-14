"""闪电添加设置（enabled/hotkey + 默认参数）：默认值、持久化往返、热键同步状态机。"""
import json
from types import SimpleNamespace

from zentray.services import settings_manager as sm_mod
from zentray.services.settings_manager import SettingsManager


def test_quick_add_defaults(tmp_data_dir):
    qa = SettingsManager.reload().quick_add
    assert qa.enabled is True
    assert qa.hotkey == ""
    assert qa.default_category == "工作"
    assert qa.default_priority == "medium"


def test_quick_add_roundtrip(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        json.dumps(
            {"quick_add": {"enabled": False, "hotkey": "<ctrl>+<alt>+q", "default_category": "生活", "default_priority": "high"}}
        ),
        encoding="utf-8",
    )
    qa = SettingsManager.reload().quick_add
    assert qa.enabled is False
    assert qa.hotkey == "<ctrl>+<alt>+q"
    assert qa.default_category == "生活"
    assert qa.default_priority == "high"


class _FakeSignal:
    def connect(self, *a):
        pass


class _FakeListener:
    def __init__(self, hotkey_str):
        self.hotkey_str = hotkey_str
        self.triggered = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.started = False


def _make_runtime():
    return SimpleNamespace(hotkey=None, on_quick_add=lambda: None)


def test_sync_quick_add_hotkey_states(monkeypatch):
    import zentray.main as main_mod

    monkeypatch.setattr(main_mod, "HotkeyListener", _FakeListener)
    rt = _make_runtime()
    # 启动注册：hotkey 空 → 平台默认常量
    main_mod._sync_quick_add_hotkey(rt, SimpleNamespace(enabled=True, hotkey=""), initial=True)
    assert rt.hotkey.hotkey_str == main_mod.HOTKEY_QUICK_ADD and rt.hotkey.started

    # 同设置再次保存：不重建
    same = rt.hotkey
    main_mod._sync_quick_add_hotkey(rt, SimpleNamespace(enabled=True, hotkey=""))
    assert rt.hotkey is same

    # 换键：停旧起新
    main_mod._sync_quick_add_hotkey(rt, SimpleNamespace(enabled=True, hotkey="<ctrl>+<alt>+q"))
    assert same.started is False
    assert rt.hotkey.hotkey_str == "<ctrl>+<alt>+q" and rt.hotkey.started

    # 关开关：停用且置空
    main_mod._sync_quick_add_hotkey(rt, SimpleNamespace(enabled=False, hotkey="<ctrl>+<alt>+q"))
    assert rt.hotkey is None
