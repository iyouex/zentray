"""提醒甲板「跳转」：closeHost 的 jump payload 由 main 捕获，关窗扫尾后开任务列表直达选中。"""
from types import SimpleNamespace


def test_jump_payload_opens_task_list(monkeypatch):
    import zentray.main as m
    import zentray.ui.vue_commands as vc

    # find_task 返回 None：扫尾直接跳过，专测 jump 分支
    task = SimpleNamespace(id="t1", title="X", reminder=SimpleNamespace(last_fired_key=None))
    runtime = SimpleNamespace(
        reminder_modal_open=False,
        reminder_queue=[],
        controller=SimpleNamespace(update_display=lambda: None),
        reminder_worker=None,
    )
    monkeypatch.setattr(
        m, "injector", SimpleNamespace(get=lambda cls: SimpleNamespace(find_task=lambda _id: None))
    )
    monkeypatch.setattr(vc, "try_vue_reminders", lambda batch: (True, {"action": "jump", "task_id": "t1"}))
    monkeypatch.setattr("zentray.ui.dialog_utils.run_modal_loop", lambda dlg: None)
    monkeypatch.setattr(m, "apply_reminder_action", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(vc, "try_vue_task_list", lambda controller, select_id=None: calls.append(select_id))

    m._on_reminder_due(runtime, [(task, "k1")])

    assert calls == ["t1"]
    assert runtime.reminder_modal_open is False


def test_non_jump_payload_skips_task_list(monkeypatch):
    import zentray.main as m
    import zentray.ui.vue_commands as vc

    task = SimpleNamespace(id="t2", title="Y", reminder=SimpleNamespace(last_fired_key=None))
    runtime = SimpleNamespace(
        reminder_modal_open=False,
        reminder_queue=[],
        controller=SimpleNamespace(update_display=lambda: None),
        reminder_worker=None,
    )
    monkeypatch.setattr(
        m, "injector", SimpleNamespace(get=lambda cls: SimpleNamespace(find_task=lambda _id: None))
    )
    monkeypatch.setattr(vc, "try_vue_reminders", lambda batch: (True, None))
    monkeypatch.setattr("zentray.ui.dialog_utils.run_modal_loop", lambda dlg: None)
    monkeypatch.setattr(m, "apply_reminder_action", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(vc, "try_vue_task_list", lambda controller, select_id=None: calls.append(select_id))

    m._on_reminder_due(runtime, [(task, "k2")])

    assert calls == []
