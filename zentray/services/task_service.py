# zentray/services/task_service.py
"""
任务管理服务 —— 封装所有任务相关业务逻辑。

将原 TrayManager 中的任务 CRUD、进度更新、完成/废弃等操作
抽取为独立服务，通过依赖注入与 UI 层解耦。
"""
from __future__ import annotations

import datetime
import uuid
from typing import List, Optional, Union

from zentray.core.models import PeriodicTemplate, Task
from zentray.core.repository import PeriodicTemplateRepository, TaskRepository
from zentray.core.scheduler import Scheduler


class TaskService:
    """任务管理服务"""

    def __init__(
        self,
        task_repo: TaskRepository,
        template_repo: PeriodicTemplateRepository,
        scheduler: Scheduler,
    ):
        self.task_repo = task_repo
        self.template_repo = template_repo
        self.scheduler = scheduler
        # 启动时立即加载已有任务
        self._refresh_scheduler()

    # ==========================================
    # 查询方法
    # ==========================================

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return self.task_repo.find_all()

    def list_archived(
        self, status: Optional[str] = None, category: Optional[str] = None, days: int = 90
    ) -> List[dict]:
        """归档任务列表（历史视图）：完成/废弃记录，时间倒序。"""
        return self.task_repo.list_archived(status=status, category=category, days=days)

    def get_current_task(self) -> Optional[Task]:
        """获取当前轮播焦点任务（始终为仓库中的原始任务，不含展示前缀）"""
        return self.scheduler.get_current()

    def get_task_display_title(self, task: Optional[Task] = None) -> str:
        """带分类前缀与逾期前缀的展示标题（不写回存储）。"""
        task = task if task is not None else self.get_current_task()
        if not task:
            return ""
        from zentray.core.categories import format_display_title_with_category
        from zentray.services.settings_manager import SettingsManager

        settings = SettingsManager()
        overdue = ""
        if (
            self.scheduler.overdue_enabled
            and task.deadline
            and self.scheduler._is_overdue(task.deadline, datetime.date.today())
        ):
            overdue = self.scheduler.overdue_prefix
        return format_display_title_with_category(
            task.title,
            settings.categories,
            primary_id=getattr(task, "category_primary_id", None),
            secondary_id=getattr(task, "category_secondary_id", None),
            category_name=task.category,
            overdue_prefix=overdue,
        )

    def advance_rotation(self):
        """推进轮播并返回当前任务。"""
        return self.scheduler.get_next()

    def get_all_templates(self) -> List[PeriodicTemplate]:
        """获取所有周期任务模板"""
        return self.template_repo.find_all()

    def find_task(self, task_id: str) -> Optional[Task]:
        return self.task_repo.find_by_id(task_id)

    # ==========================================
    # 任务 CRUD
    # ==========================================

    def create_task(self, task_data: dict) -> Union[Task, PeriodicTemplate]:
        """
        创建新任务或周期模板。

        当 task_type == "periodic" 或提供 periodicity 时，写入模板库，
        并尝试立即派发当前周期实例。
        """
        is_periodic = (
            task_data.get("task_type") == "periodic"
            or bool(task_data.get("periodicity"))
        )
        if is_periodic:
            return self.create_template(task_data)

        # 过滤非法 task_type，统一为 one-time
        clean = {**task_data, "task_type": "one-time"}
        # 去掉仅模板字段
        clean.pop("periodicity", None)
        clean = self._normalize_category_fields(clean)
        clean = self._normalize_reminder_field(clean)
        task = Task.from_dict(clean)
        tasks = self.task_repo.find_all()
        tasks.append(task)
        self.task_repo.save_all(tasks)
        self._refresh_scheduler()
        try:
            from zentray.services.activity_log import log_event

            log_event(
                "task",
                "create",
                task.title,
                f"优先级={task.priority}",
                meta={"id": task.id},
            )
        except Exception:
            pass
        return task

    def create_template(self, data: dict) -> PeriodicTemplate:
        """创建周期任务模板，并立即生成当前周期实例（若尚未生成）。"""
        tmpl = self._template_from_data(data)
        templates = self.template_repo.find_all()
        templates.append(tmpl)
        self.template_repo.save_all(templates)

        self._spawn_template_instance_if_needed(tmpl)
        templates = self.template_repo.find_all()
        for i, t in enumerate(templates):
            if t.template_id == tmpl.template_id:
                templates[i] = tmpl
                break
        self.template_repo.save_all(templates)
        self._refresh_scheduler()
        return tmpl

    def update_template(
        self, template_id: str, data: dict
    ) -> Optional[PeriodicTemplate]:
        """更新周期模板（不强制立刻改历史实例）。"""
        templates = self.template_repo.find_all()
        for i, t in enumerate(templates):
            if t.template_id == template_id:
                merged = {**t.to_dict(), **data, "template_id": template_id}
                # base_title 兼容 title
                if data.get("title") and not data.get("base_title"):
                    merged["base_title"] = data["title"]
                tmpl = self._template_from_data(merged)
                tmpl.template_id = template_id
                tmpl.last_generated_period = t.last_generated_period
                templates[i] = tmpl
                self.template_repo.save_all(templates)
                self._spawn_template_instance_if_needed(tmpl)
                # 回写 last_generated
                templates = self.template_repo.find_all()
                for j, tt in enumerate(templates):
                    if tt.template_id == template_id:
                        templates[j] = tmpl
                        break
                self.template_repo.save_all(templates)
                self._refresh_scheduler()
                return tmpl
        return None

    def delete_template(self, template_id: str) -> bool:
        templates = [
            t for t in self.template_repo.find_all() if t.template_id != template_id
        ]
        before = len(self.template_repo.find_all())
        self.template_repo.save_all(templates)
        return len(templates) < before

    def skip_template(
        self, template_id: str, count: int
    ) -> Optional[PeriodicTemplate]:
        """跳过接下来 count 个未派发周期（推进水位，不产生实例）。"""
        tmpl = self.find_template(template_id)
        if not tmpl:
            return None
        from zentray.core.periodic import skip_watermark_key

        # 原地改水位（不走 _template_from_data，避免白名单重建丢字段），不触发派发
        tmpl.last_generated_period = skip_watermark_key(
            tmpl, datetime.date.today(), max(1, int(count))
        )
        templates = self.template_repo.find_all()
        for i, t in enumerate(templates):
            if t.template_id == template_id:
                templates[i] = tmpl
                break
        self.template_repo.save_all(templates)
        self._refresh_scheduler()
        return tmpl

    def find_template(self, template_id: str) -> Optional[PeriodicTemplate]:
        for t in self.template_repo.find_all():
            if t.template_id == template_id:
                return t
        return None

    def update_task(self, task_id: str, task_data: dict) -> Optional[Task]:
        """更新任务字段并刷新调度器"""
        # 防止把周期 UI 字段写进 Task；允许 periodic_instance 保持实例类型
        task_data = {
            k: v
            for k, v in task_data.items()
            if k
            not in (
                "periodicity",
                "interval",
                "long_term",
                "schedule_end_date",
                "deadline_weekday",
                "deadline_day_of_month",
            )
        }
        if task_data.get("task_type") == "periodic":
            task_data = {**task_data, "task_type": "one-time"}
        task_data = self._normalize_category_fields(task_data)
        task_data = self._normalize_reminder_field(task_data)

        tasks = self.task_repo.find_all()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                base = t.to_dict()
                updated = Task.from_dict({**base, **task_data, "id": task_id})
                tasks[i] = updated
                self.task_repo.save_all(tasks)
                self._refresh_scheduler()
                try:
                    from zentray.services.activity_log import log_event

                    log_event(
                        "task",
                        "update",
                        updated.title,
                        "编辑任务",
                        meta={"id": task_id},
                    )
                except Exception:
                    pass
                return updated
        return None

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        task = self.task_repo.find_by_id(task_id)
        if task:
            self.task_repo.delete(task_id)
            self._refresh_scheduler()
            return True
        return False

    # ==========================================
    # 任务状态操作
    # ==========================================

    def select_task(self, task_id: str) -> None:
        """将指定任务设为当前轮播焦点（不缩减队列）。"""
        task = self.task_repo.find_by_id(task_id)
        if task:
            self.scheduler.focus(task)
            try:
                from zentray.services.activity_log import log_event

                log_event(
                    "task",
                    "select",
                    task.title,
                    "切换到此任务",
                    meta={"id": task_id},
                )
            except Exception:
                pass

    def mark_done(self, task_id: str) -> None:
        """完成任务：归档 + 删除"""
        task = self.task_repo.find_by_id(task_id)
        if task:
            self.task_repo.archive(task, "DONE")
            self.task_repo.delete(task_id)
            self._refresh_scheduler()
            try:
                from zentray.services.activity_log import log_event

                log_event(
                    "task",
                    "done",
                    task.title,
                    "完成并归档",
                    meta={"id": task_id},
                )
            except Exception:
                pass

    def abandon(self, task_id: str) -> None:
        """废弃任务：归档 + 删除"""
        task = self.task_repo.find_by_id(task_id)
        if task:
            self.task_repo.archive(task, "ABANDONED")
            self.task_repo.delete(task_id)
            self._refresh_scheduler()
            try:
                from zentray.services.activity_log import log_event

                log_event(
                    "task",
                    "abandon",
                    task.title,
                    "废弃并归档",
                    meta={"id": task_id},
                )
            except Exception:
                pass

    def update_progress(self, task_id: str, percent: int, note: str = "") -> Optional[Task]:
        """更新任务进度百分比和日志（进度对齐到 10% 步进）。"""
        # 仅允许 0/10/…/100，与托盘饼图资源、UI 拖拽一致
        try:
            pct = int(percent)
        except (TypeError, ValueError):
            pct = 0
        pct = max(0, min(100, pct))
        pct = int(round(pct / 10.0) * 10)
        pct = max(0, min(100, pct))

        tasks = self.task_repo.find_all()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                t.progress = pct
                t.progress_logs.append({
                    "time": datetime.datetime.now().isoformat(timespec="seconds"),
                    "percent": t.progress,
                    "note": note,
                })
                tasks[i] = t
                self.task_repo.save_all(tasks)
                self._refresh_scheduler()
                try:
                    from zentray.services.activity_log import log_event

                    log_event(
                        "task",
                        "progress",
                        t.title,
                        f"进度→{pct}%" + (f" · {note}" if note else ""),
                        meta={"id": task_id, "percent": pct},
                    )
                except Exception:
                    pass
                return t
        return None

    # ==========================================
    # 模板操作
    # ==========================================

    def save_templates(self, templates: List[PeriodicTemplate]) -> None:
        """保存周期任务模板"""
        self.template_repo.save_all(templates)

    # ==========================================
    # 内部方法
    # ==========================================

    def refresh_scheduler(self) -> None:
        """刷新调度器队列（供外部调用，如 watcher 更新后）"""
        self._refresh_scheduler()

    def _refresh_scheduler(self) -> None:
        """重新从存储加载活跃任务并构建调度队列"""
        tasks = self.task_repo.find_active()
        from zentray.services.settings_manager import SettingsManager

        settings = SettingsManager()
        self.scheduler.configure(
            mode=settings.polling.rotation_mode,
            overdue_enabled=settings.polling.enable_overdue_rotation,
            overdue_prefix=settings.polling.overdue_prefix,
        )
        self.scheduler.build_queue(tasks)

    def _spawn_template_instance_if_needed(self, tmpl: PeriodicTemplate) -> None:
        """若当前周期尚未派发，则创建实例任务。"""
        from zentray.core.periodic import build_due_instance

        new_task = build_due_instance(tmpl, datetime.date.today())
        if new_task is None:
            return
        tasks = self.task_repo.find_all()
        tasks.append(new_task)
        self.task_repo.save_all(tasks)

    def _template_from_data(self, data: dict) -> PeriodicTemplate:
        from zentray.core.reminder import TaskReminder

        title = (data.get("title") or data.get("base_title") or "Untitled").strip()
        rem = data.get("reminder")
        if isinstance(rem, dict):
            rem = TaskReminder.from_dict(rem)
        try:
            interval = max(1, int(data.get("interval") or 1))
        except (TypeError, ValueError):
            interval = 1
        long_term = data.get("long_term")
        if long_term is None:
            long_term = True
        else:
            long_term = bool(long_term)
        return PeriodicTemplate(
            base_title=title,
            category=data.get("category") or "工作",
            periodicity=data.get("periodicity") or "daily",
            details=data.get("details") or "",
            priority=data.get("priority") or "medium",
            category_primary_id=data.get("category_primary_id"),
            category_secondary_id=data.get("category_secondary_id"),
            reminder=rem,
            interval=interval,
            deadline_weekday=data.get("deadline_weekday"),
            deadline_day_of_month=data.get("deadline_day_of_month"),
            auto_abandon_on_overdue=bool(data.get("auto_abandon_on_overdue", False)),
            long_term=long_term,
            schedule_end_date=(data.get("schedule_end_date") or None) or None,
            paused=bool(data.get("paused", False)),
            template_id=data.get("template_id") or str(uuid.uuid4()),
            last_generated_period=data.get("last_generated_period"),
        )

    def _normalize_category_fields(self, data: dict) -> dict:
        """补齐 category 与 primary/secondary id。"""
        from zentray.services.settings_manager import SettingsManager

        cats = SettingsManager().categories
        data = {**data}
        primary_id = data.get("category_primary_id")
        name = data.get("category") or "工作"
        primary = cats.find_primary(primary_id) or cats.find_primary_by_name(name)
        if primary is None:
            primary = cats.ensure_primary_named(name)
        data["category_primary_id"] = primary.id
        data["category"] = primary.name
        if not cats.enabled_secondary:
            data["category_secondary_id"] = None
        return data

    @staticmethod
    def _normalize_reminder_field(data: dict) -> dict:
        from zentray.core.reminder import TaskReminder

        data = {**data}
        rem = data.get("reminder")
        if rem is None:
            return data
        if isinstance(rem, dict):
            data["reminder"] = TaskReminder.from_dict(rem)
        return data

    def update_task_reminder(self, task_id: str, reminder) -> Optional[Task]:
        """更新任务提醒状态（如 last_fired / snooze）。"""
        tasks = self.task_repo.find_all()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                t.reminder = reminder
                tasks[i] = t
                self.task_repo.save_all(tasks)
                return t
        return None
