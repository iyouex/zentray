"""关联插件随任务弹窗运行（task_popup 触发源）。"""
from types import SimpleNamespace

from zentray.core.models import Task
from zentray.workers.reminder_job import ReminderWorker


class _Runtime:
    """run_script 假体：记录调用；可注入 busy/番茄态。"""

    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def run_script(self, plug, *, pomodoro_active=False, task=None, trigger="manual"):
        self.calls.append(
            {"id": plug.manifest.id, "pomodoro": pomodoro_active,
             "task": task, "trigger": trigger}
        )
        return self.ok


def _worker(task_repo, runtime, *, enabled=True, pomodoro=False):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.enabled = enabled
    sm.save()
    worker = ReminderWorker(task_repo)
    worker.plugin_loader = SimpleNamespace(
        get=lambda pid: SimpleNamespace(manifest=SimpleNamespace(id=pid)) if pid == "chaowen" else None
    )
    worker.plugin_runtime = runtime
    worker.pomodoro_service = SimpleNamespace(is_active=pomodoro)
    return worker


def _task(tid, plugin_id=None):
    return Task(id=tid, title=f"t-{tid}", category="工作", plugin_id=plugin_id)


def test_popup_runs_associated_plugin(task_repo):
    rt = _Runtime()
    w = _worker(task_repo, rt, pomodoro=True)
    t = _task("a1", plugin_id="chaowen")
    w._run_task_plugins([(t, "due")])
    assert len(rt.calls) == 1
    assert rt.calls[0] == {
        "id": "chaowen", "pomodoro": True, "task": t, "trigger": "task_popup"
    }


def test_no_plugin_id_or_unknown_plugin_skipped(task_repo):
    rt = _Runtime()
    w = _worker(task_repo, rt)
    w._run_task_plugins([(_task("a1"), "due"), (_task("a2", plugin_id="nope"), "dlv|x")])
    assert rt.calls == []  # 无关联/插件不存在：不触发


def test_same_task_deduped_within_batch(task_repo):
    rt = _Runtime()
    w = _worker(task_repo, rt)
    t = _task("a1", plugin_id="chaowen")
    w._run_task_plugins([(t, "dlv|2026-10-20T08:00"), (t, "dlv|2026-10-20T09:00")])
    assert len(rt.calls) == 1


def test_busy_plugin_or_ops_disabled_silent(task_repo):
    # busy（run_script 返回 False）：静默不重试
    w = _worker(task_repo, _Runtime(ok=False))
    w._run_task_plugins([(_task("a1", plugin_id="chaowen"), "due")])
    # 插件总开关关闭：不触发
    rt = _Runtime()
    w2 = _worker(task_repo, rt, enabled=False)
    w2._run_task_plugins([(_task("a1", plugin_id="chaowen"), "due")])
    assert rt.calls == []


def test_no_deps_injected_is_noop(task_repo):
    w = ReminderWorker(task_repo)
    w._run_task_plugins([(_task("a1", plugin_id="chaowen"), "due")])  # 不抛错
