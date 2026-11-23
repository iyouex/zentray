"""UpdateWatcher：静默检查的触发条件、每版本一次的通知、替换失败上报、状态变化转发。"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # noqa: E402 须在 Qt 实例化之前

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from zentray.services import updater  # noqa: E402
from zentray.services.update_watcher import INITIAL_DELAY_MS, INTERVAL_MS, UpdateWatcher  # noqa: E402

FOUND = {"has_update": True, "version": "9.9.9"}


class _FakeService:
    """记录调用、可手动触发回调的 UpdaterService 替身。"""

    def __init__(self):
        self.state = "idle"
        self.starts = []  # (proxy, manual)
        self.listeners = []
        self.pending = []  # 尚未回调的 on_done

    def subscribe(self, callback):
        self.listeners.append(callback)

    def status(self):
        return {"state": self.state}

    def start_check(self, proxy="", manual=True, on_done=None):
        self.starts.append((proxy, manual))
        self.pending.append(on_done)
        return {"started": True, "state": "checking"}


@pytest.fixture
def app():
    # 已有实例就复用。没有时创建 GUI 应用而非 QCoreApplication：PySide 会让它活到会话
    # 结束，而一个残留的非 GUI 实例会让后续用例里的 QPixmap 绘制直接中止进程。
    return QCoreApplication.instance() or QApplication(["zentray-update-tests"])


@pytest.fixture(autouse=True)
def isolated_updates_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "UPDATES_DIR", tmp_path / "updates")


@pytest.fixture
def service(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(updater.UpdaterService, "_instance", fake)
    return fake


def _until(condition, app, timeout=5.0):
    """跑事件循环直到条件成立（QTimer.singleShot 需要事件循环才会触发）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError("条件未在限定时间内成立")


def _watcher(service, app, initial_delay_ms=20, interval_ms=60000):
    watcher = UpdateWatcher(initial_delay_ms=initial_delay_ms, interval_ms=interval_ms)
    return watcher


def test_schedule_matches_the_reference_behavior():
    assert INITIAL_DELAY_MS == 4000
    assert INTERVAL_MS == 6 * 60 * 60 * 1000


def test_start_checks_silently_once_after_the_initial_delay(service, app, tmp_data_dir):
    watcher = _watcher(service, app)
    watcher.start()
    assert service.starts == []  # 不是启动瞬间就查

    _until(lambda: service.starts, app)

    assert service.starts == [("", False)]  # 静默检查，代理取自设置
    assert watcher._timer.isActive() and watcher._timer.interval() == 60000
    watcher.stop()
    assert not watcher._timer.isActive()


def test_check_is_skipped_when_auto_check_is_off(service, app, tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    watcher = _watcher(service, app)
    watcher.start()
    _until(lambda: service.starts, app)
    assert len(service.starts) == 1

    SettingsManager().update.auto_check = False
    watcher.check_now()
    time.sleep(0.05)
    assert len(service.starts) == 1  # 关掉自动检查后不再发起


@pytest.mark.parametrize("state", ["checking", "downloading", "ready", "installing",
                                   "installed"])
def test_check_is_skipped_while_an_update_is_in_flight(service, app, tmp_data_dir, state):
    service.state = state
    _watcher(service, app).check_now()
    time.sleep(0.05)
    assert service.starts == []


def test_check_clears_leftovers_before_probing(service, app, tmp_data_dir, monkeypatch):
    order = []
    monkeypatch.setattr(updater, "cleanup_stale", lambda: order.append("cleanup"))
    service.start_check = lambda proxy="", manual=True, on_done=None: order.append("check")

    _watcher(service, app).check_now()
    _until(lambda: "check" in order, app)

    assert order == ["cleanup", "check"]


def test_found_is_emitted_once_per_version(service, app, tmp_data_dir):
    watcher = _watcher(service, app)
    found = []
    watcher.found.connect(found.append)

    watcher._checked(FOUND, "")  # 首次发现
    watcher._checked(FOUND, "")  # 下次定时检查、甚至重启之后：同一版本不再通知
    watcher._checked({**FOUND, "version": "10.0.0"}, "")  # 更新的版本才再通知一次
    watcher._checked({"has_update": False, "version": "0.0.1"}, "")  # 没有更新
    watcher._checked(None, "检查更新失败：boom")  # 静默检查失败不打扰

    assert found == ["9.9.9", "10.0.0"]
    assert updater.notified_versions() == {"9.9.9", "10.0.0"}


def test_a_version_the_user_found_manually_is_not_announced_again(service, app, tmp_data_dir):
    watcher = _watcher(service, app)
    found = []
    watcher.found.connect(found.append)
    assert len(service.listeners) == 1
    on_state = service.listeners[0]

    on_state({"state": "available", "manual": True, "result": FOUND})

    watcher._checked(FOUND, "")
    assert found == []  # 用户已经在设置页看到了


def test_every_state_change_is_forwarded(service, app, tmp_data_dir):
    watcher = _watcher(service, app)
    changes = []
    watcher.changed.connect(lambda: changes.append(1))
    on_state = service.listeners[0]

    on_state({"state": "downloading", "manual": False, "result": FOUND})
    on_state({"state": "ready", "manual": False, "result": FOUND})

    assert changes == [1, 1]


def test_a_failed_swap_from_the_previous_run_is_reported(service, app, tmp_data_dir):
    updater.UPDATES_DIR.mkdir(parents=True)
    updater._swap_result_file().write_text("ok=0\nreason=swap_failed\n")
    watcher = _watcher(service, app, initial_delay_ms=60000)
    failures = []
    watcher.swap_failed.connect(failures.append)

    watcher.start()

    assert failures == ["swap_failed"]
    assert updater.pop_swap_result() is None  # 只报一次


def test_a_successful_swap_is_not_reported(service, app, tmp_data_dir):
    updater.UPDATES_DIR.mkdir(parents=True)
    updater._swap_result_file().write_text("ok=1\nreason=\n")
    watcher = _watcher(service, app, initial_delay_ms=60000)
    failures = []
    watcher.swap_failed.connect(failures.append)

    watcher.start()

    assert failures == []


def test_check_conditions_are_read_from_settings(service, app, tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    SettingsManager().update.proxy = "http://127.0.0.1:7897"
    watcher = _watcher(service, app)

    watcher.check_now()
    _until(lambda: service.starts, app)

    assert service.starts == [("http://127.0.0.1:7897", False)]


def test_unreadable_settings_do_not_break_the_tick(service, app, tmp_data_dir, monkeypatch):
    from zentray.services import update_watcher

    def explode():
        raise OSError("settings unreadable")

    monkeypatch.setattr(update_watcher, "SettingsManager", explode)
    _watcher(service, app).check_now()
    time.sleep(0.05)
    assert service.starts == []


def test_start_survives_a_broken_swap_result_file(service, app, tmp_data_dir, monkeypatch):
    def explode():
        raise OSError("disk gone")

    monkeypatch.setattr(updater, "pop_swap_result", explode)
    watcher = _watcher(service, app, initial_delay_ms=60000)
    watcher.start()  # 读不出上次替换结果不应拖垮启动
    watcher.stop()


def test_subscribes_to_the_shared_service_once(service, app, tmp_data_dir):
    watcher = UpdateWatcher(initial_delay_ms=60000)
    assert service.listeners == [watcher._on_service_state]
