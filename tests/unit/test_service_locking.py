# tests/unit/test_service_locking.py
"""D4 写互斥：多线程并发 RMW 不得丢任务/丢模板（无锁时 find_all→save_all 交错互相覆盖）。"""
import threading

from zentray.core.models import Task
from zentray.core.scheduler import Scheduler
from zentray.repositories.file_periodic_repository import FilePeriodicTemplateRepository
from zentray.repositories.file_repository import FileTaskRepository
from zentray.services.task_service import TaskService


def _svc(tmp_data_dir):
    return TaskService(
        FileTaskRepository(),
        FilePeriodicTemplateRepository(),
        Scheduler(),
    )


def test_concurrent_create_task_no_loss(tmp_data_dir):
    svc = _svc(tmp_data_dir)
    n_threads, per_thread = 6, 8
    barrier = threading.Barrier(n_threads)

    def worker(k):
        barrier.wait()  # 尽量同刻起跑，放大交错窗口
        for j in range(per_thread):
            svc.create_task({"title": f"t{k}-{j}", "category": "工作"})

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(svc.get_all_tasks()) == n_threads * per_thread


def test_concurrent_template_write_no_loss(tmp_data_dir):
    svc = _svc(tmp_data_dir)
    base = svc.create_template(
        {"title": "模板A", "category": "工作", "periodicity": "daily"}
    )
    n_threads = 6
    barrier = threading.Barrier(n_threads)

    def worker(k):
        barrier.wait()
        svc.update_template(base.template_id, {"title": f"模板A-{k}"})

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 6 次更新全部落在同一模板上：最终仍恰好 1 条，且水位/标题字段完好
    all_tmpls = svc.template_repo.find_all()
    assert len(all_tmpls) == 1
    assert all_tmpls[0].base_title.startswith("模板A-")


def test_repository_save_all_locks_itself(tmp_data_dir):
    """save_all 自带互斥：直接并发调用（绕过 service）也不交错。"""
    repo = FileTaskRepository()
    n_threads, per_thread = 4, 10
    barrier = threading.Barrier(n_threads)

    def worker(k):
        barrier.wait()
        for j in range(per_thread):
            task = Task(id=f"w{k}-{j}", title=f"w{k}-{j}", category="工作")
            repo.save(task)  # save = 锁内 RMW

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(repo.find_all()) == n_threads * per_thread


def test_default_repo_paths_follow_patched_config(tmp_data_dir, monkeypatch):
    """隔离回归：默认构造的仓库必须解析到当前 config 路径（迟绑定），
    防止测试静默写真实用户数据（2026-11-12 事故）。"""
    from zentray.repositories.file_repository import FileTaskRepository
    from zentray.repositories.file_periodic_repository import (
        FilePeriodicTemplateRepository,
    )

    assert FileTaskRepository().active_file == tmp_data_dir / "active_tasks.json"
    assert FileTaskRepository().archive_dir == tmp_data_dir / "archive"
    assert (
        FilePeriodicTemplateRepository().filepath
        == tmp_data_dir / "periodic_templates.json"
    )
