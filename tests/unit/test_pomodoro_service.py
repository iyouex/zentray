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
