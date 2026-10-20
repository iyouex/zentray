"""闪电添加「跳转新建任务」：closeHost 的 open_new_task payload 由宿主捕获，
浮层关闭后链式打开完整任务表单（同 Glance→quick_add 范式）。"""
from types import SimpleNamespace


def test_open_new_task_chains_to_task_form(monkeypatch):
    import zentray.ui.vue_commands as vc

    calls = []

    def fake_open(route, *, title=None, width=None, height=None, **kw):
        calls.append((route, title, width, height))
        if route == "/quick-add":
            return True, {"action": "open_new_task"}
        return True, None

    monkeypatch.setattr(vc, "use_vue_ui", lambda: True)
    monkeypatch.setattr(vc, "open_vue_route", fake_open)

    controller = SimpleNamespace(reload_data=lambda: None)
    assert vc.try_vue_quick_add(controller) is True
    # 第二跳：几何照抄 try_vue_edit_task
    assert calls[1] == ("/tasks/new", "新建任务", 960, 620)


def test_quick_add_frontend_has_jump_button():
    from pathlib import Path

    vue = Path(__file__).resolve().parents[2] / "web/src/views/QuickAdd.vue"
    src = vue.read_text(encoding="utf-8")
    assert "open_new_task" in src
    assert "qa-actions" in src
    # 跳转按钮不受 aiOn 门控（无 aiOn 的 v-if 包裹 qa-new-btn）
    assert 'class="qa-new-btn"' in src
    assert 'v-if="aiOn"' not in src.split('class="qa-new-btn"')[0].split("<a-button")[-1]
