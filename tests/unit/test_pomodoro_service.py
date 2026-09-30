# tests/unit/test_pomodoro_service.py
"""
PomodoroService 单元测试
"""
import pytest
from zentray.services.pomodoro_service import PomodoroService


class TestPomodoroService:
    """番茄钟服务核心功能测试"""

    def test_initial_state(self):
        """验证初始状态：未激活、剩余时间为0"""
        service = PomodoroService()
        assert not service.is_active
        assert service.get_remaining() == 0

    def test_start_sets_active(self):
        """验证 start() 激活计时"""
        service = PomodoroService()
        service.start()
        assert service.is_active
        assert service.get_remaining() > 0

    def test_stop_deactivates(self):
        """验证 stop() 中止计时"""
        service = PomodoroService()
        service.start()
        service.stop()
        assert not service.is_active
        assert service.get_remaining() == 0

    def test_extend_adds_time(self):
        """验证 extend() 增加剩余时间"""
        service = PomodoroService(duration_minutes=25)
        service.start()
        before = service.get_remaining()
        service.extend(10)
        after = service.get_remaining()
        assert after == before + 10 * 60


class TestPomodoroCycle:
    """专注-短休/长休循环状态机（手动驱动 _tick 快进阶段）"""

    @staticmethod
    def _make_service(
        monkeypatch,
        *,
        duration=25,
        short=5,
        long_break=15,
        every=4,
        auto_break=True,
        auto_focus=False,
    ):
        import zentray.services.pomodoro_service as mod

        monkeypatch.setattr(mod, "_settings_duration_minutes", lambda: duration)
        monkeypatch.setattr(mod, "_settings_break_minutes", lambda lb: long_break if lb else short)
        monkeypatch.setattr(mod, "_settings_long_break_every", lambda: every)
        monkeypatch.setattr(
            mod,
            "_settings_auto",
            lambda flag: auto_break if flag == "auto_start_breaks" else auto_focus,
        )
        return PomodoroService(duration)

    @staticmethod
    def _finish_phase(service):
        """把当前阶段快进到走完（触发阶段流转）。"""
        service.remaining_seconds = 0
        service._tick()

    def test_focus_end_enters_short_break(self, monkeypatch):
        svc = self._make_service(monkeypatch, short=5)
        focus_done = []
        svc.pomodoro_finished.connect(lambda: focus_done.append(True))
        svc.start(task_id="t1", task_title="写方案")
        self._finish_phase(svc)
        assert focus_done == [True]
        assert svc.phase == "short_break"
        assert svc.get_remaining() == 5 * 60
        assert svc.is_active and svc.is_break
        assert svc.completed_focus == 1
        assert svc.last_focus_seconds == 25 * 60
        # 绑定保留到休息段（供自动衔接下一段专注与日志）
        assert svc.task_id == "t1"

    def test_long_break_every_n(self, monkeypatch):
        svc = self._make_service(monkeypatch, every=4)
        phases = []
        for _ in range(4):
            svc.start()
            self._finish_phase(svc)  # 专注结束 → 休息
            phases.append(svc.phase)
            self._finish_phase(svc)  # 休息结束 → idle
        assert phases == ["short_break"] * 3 + ["long_break"]
        # 长休走完 → 节奏计数归零
        assert svc.completed_focus == 0

    def test_auto_break_off_returns_idle(self, monkeypatch):
        svc = self._make_service(monkeypatch, auto_break=False)
        svc.start()
        self._finish_phase(svc)
        assert svc.phase == "idle"
        assert not svc.is_active
        assert svc.get_remaining() == 0

    def test_break_end_idle_and_binding_cleared(self, monkeypatch):
        svc = self._make_service(monkeypatch)
        break_done = []
        svc.break_finished.connect(lambda: break_done.append(True))
        svc.start(task_id="t1", task_title="写方案")
        self._finish_phase(svc)
        self._finish_phase(svc)  # 休息结束（auto_focus 关）→ idle
        assert break_done == [True]
        assert svc.phase == "idle"
        assert svc.task_id == ""

    def test_auto_focus_chains_next_focus_with_binding(self, monkeypatch):
        svc = self._make_service(monkeypatch, auto_focus=True)
        svc.start(task_id="t1", task_title="写方案")
        self._finish_phase(svc)
        self._finish_phase(svc)  # 休息结束 → 自动开始下一段专注
        assert svc.phase == "focus"
        assert svc.get_remaining() == 25 * 60
        assert svc.task_id == "t1" and svc.task_title == "写方案"

    def test_skip_break(self, monkeypatch):
        svc = self._make_service(monkeypatch)
        break_done = []
        svc.break_finished.connect(lambda: break_done.append(True))
        svc.start()
        self._finish_phase(svc)
        svc.skip_break()
        assert svc.phase == "idle"
        assert break_done == [True]
        assert svc.completed_focus == 1  # 节奏保留：下次专注结束仍可进长休

    def test_stop_during_focus_returns_elapsed(self, monkeypatch):
        svc = self._make_service(monkeypatch, duration=25)
        svc.start()
        svc.remaining_seconds = 25 * 60 - 120  # 已专注 2 分钟
        elapsed = svc.stop()
        assert elapsed == 120
        assert svc.last_focus_seconds == 120
        assert not svc.is_active and svc.get_remaining() == 0
        assert svc.task_id == ""

    def test_stop_during_break(self, monkeypatch):
        svc = self._make_service(monkeypatch)
        svc.start()
        self._finish_phase(svc)
        assert svc.is_break
        svc.stop()
        assert svc.phase == "idle"

    def test_extend_only_in_focus(self, monkeypatch):
        svc = self._make_service(monkeypatch)
        svc.start()
        before = svc.get_remaining()
        svc.extend(10)
        assert svc.get_remaining() == before + 600
        self._finish_phase(svc)  # 进休息
        svc.extend(10)
        assert svc.get_remaining() == 5 * 60  # 休息段延长无效

    def test_long_break_every_zero_never_long(self, monkeypatch):
        svc = self._make_service(monkeypatch, every=0)
        for _ in range(6):
            svc.start()
            self._finish_phase(svc)
            assert svc.phase == "short_break"
            self._finish_phase(svc)


def test_pomodoro_settings_new_fields_roundtrip(tmp_data_dir):
    """新设置字段：默认值、持久化往返、旧配置文件回退默认。"""
    import json

    from zentray.services import settings_manager as sm_mod
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    assert sm.pomodoro.short_break_minutes == 5
    assert sm.pomodoro.long_break_minutes == 15
    assert sm.pomodoro.long_break_every == 4
    assert sm.pomodoro.auto_start_breaks is True
    assert sm.pomodoro.auto_start_focus is False
    assert sm.pomodoro.daily_goal_pomodoros == 0

    # 旧格式配置（无新键）→ 新字段取默认
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"pomodoro": {"duration_minutes": 50}}), encoding="utf-8")
    sm = SettingsManager.reload()
    assert sm.pomodoro.duration_minutes == 50
    assert sm.pomodoro.short_break_minutes == 5

    sm.pomodoro.short_break_minutes = 10
    sm.pomodoro.long_break_every = 2
    sm.pomodoro.daily_goal_pomodoros = 8
    sm.save()
    sm2 = SettingsManager.reload()
    assert sm2.pomodoro.short_break_minutes == 10
    assert sm2.pomodoro.long_break_every == 2
    assert sm2.pomodoro.daily_goal_pomodoros == 8
