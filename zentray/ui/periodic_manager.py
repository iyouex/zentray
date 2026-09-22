"""周期任务模板管理对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from zentray.core.models import PeriodicTemplate
from zentray.ui.dialogs import TaskDialog
from zentray.ui.dialog_utils import apply_dialog_chrome, run_modal_loop, style_action_button


class PeriodicManagerDialog(QDialog):
    """列表管理周期模板：新建 / 编辑 / 删除。"""

    def __init__(self, task_service, parent=None):
        super().__init__(parent)
        self.task_service = task_service
        self.setWindowTitle("周期任务管理")
        apply_dialog_chrome(self, width=720, height=400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        hint = QLabel(
            "周期任务模板（调度生成的实例可在任务列表中像普通任务一样编辑）"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._edit_selected)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        btn_new = style_action_button(QPushButton("➕ 新建周期任务"), min_w=130)
        btn_new.clicked.connect(self._new_template)
        btn_edit = style_action_button(QPushButton("📝 编辑"), min_w=88)
        btn_edit.clicked.connect(self._edit_selected)
        btn_del = style_action_button(QPushButton("🗑 删除"), min_w=88)
        btn_del.clicked.connect(self._delete_selected)
        btn_close = style_action_button(QPushButton("关闭"), min_w=80)
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_new)
        row.addWidget(btn_edit)
        row.addWidget(btn_del)
        row.addStretch()
        row.addWidget(btn_close)
        layout.addLayout(row)

        self._reload()

    def _reload(self):
        self.list.clear()
        for t in self.task_service.get_all_templates():
            interval = max(1, int(getattr(t, "interval", 1) or 1))
            unit = {"daily": "天", "weekly": "周", "monthly": "月"}.get(
                t.periodicity, "天"
            )
            life = "长期" if getattr(t, "long_term", True) else (
                f"至 {getattr(t, 'schedule_end_date', '') or '?'}"
            )
            abandon = "·逾期废弃" if getattr(t, "auto_abandon_on_overdue", False) else ""
            label = f"{t.base_title}  |  每{interval}{unit}  |  {life}{abandon}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, t.template_id)
            self.list.addItem(item)

    def _selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _new_template(self):
        dlg = TaskDialog(self)
        # 强制周期模式
        dlg.rb_periodic.setChecked(True)
        dlg._on_type_toggled()
        if run_modal_loop(dlg):
            data = dlg.get_data()
            data["task_type"] = "periodic"
            self.task_service.create_task(data)
            self._reload()

    def _edit_selected(self):
        tid = self._selected_id()
        if not tid:
            return
        tmpl = self.task_service.find_template(tid)
        if not tmpl:
            return
        dlg = TaskDialog(self, task=tmpl)
        if run_modal_loop(dlg):
            data = dlg.get_data()
            self.task_service.update_template(tid, data)
            self._reload()

    def _delete_selected(self):
        tid = self._selected_id()
        if not tid:
            return
        tmpl = self.task_service.find_template(tid)
        name = tmpl.base_title if tmpl else tid
        ret = QMessageBox.question(
            self,
            "删除周期模板",
            f"确定删除周期任务「{name}」？\n已生成的实例任务不会自动删除。",
        )
        if ret == QMessageBox.Yes:
            self.task_service.delete_template(tid)
            self._reload()
