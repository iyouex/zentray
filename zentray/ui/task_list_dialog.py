"""任务列表面板：左侧固定高度可滚动列表 + 右侧操作。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from zentray.ui.dialog_utils import apply_dialog_chrome, style_action_button


class TaskListDialog(QDialog):
    """
    横版：左任务列表（可滚动）+ 右操作面板。
    """

    def __init__(self, task_service, parent=None):
        super().__init__(parent)
        self.task_service = task_service
        self.selected_action = None  # (action, task_id) or None
        self.setWindowTitle("任务列表")
        apply_dialog_chrome(self, width=720, height=420)

        self._list_collapsed = False
        self._tasks = []

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(14)

        # ---- 左侧 ----
        left = QVBoxLayout()
        left.setSpacing(6)

        header = QHBoxLayout()
        self.lbl_header = QLabel("📋 任务列表")
        self.lbl_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self.lbl_header)
        header.addStretch()
        self.btn_fold = style_action_button(QPushButton("收起 ▲"), min_w=80, min_h=30)
        self.btn_fold.clicked.connect(self._toggle_list)
        header.addWidget(self.btn_fold)
        left.addLayout(header)

        self.list_frame = QFrame()
        self.list_frame.setFrameShape(QFrame.StyledPanel)
        fl = QVBoxLayout(self.list_frame)
        fl.setContentsMargins(0, 0, 0, 0)
        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(200)
        self.task_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.task_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.task_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.task_list.currentItemChanged.connect(self._on_select)
        fl.addWidget(self.task_list)
        left.addWidget(self.list_frame, 1)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #888; font-size: 11px;")
        left.addWidget(self.lbl_count)
        root.addLayout(left, 3)

        # ---- 右侧操作 ----
        right = QVBoxLayout()
        right.setSpacing(8)
        self.lbl_task = QLabel("请选择左侧任务")
        self.lbl_task.setWordWrap(True)
        self.lbl_task.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.lbl_task.setMinimumWidth(200)
        right.addWidget(self.lbl_task)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setStyleSheet("color: #888; font-size: 12px;")
        right.addWidget(self.lbl_meta)

        right.addSpacing(6)
        self.btn_select = style_action_button(QPushButton("🔄 切换到此任务"), min_w=140)
        self.btn_select.clicked.connect(lambda: self._act("select"))
        right.addWidget(self.btn_select)
        self.btn_progress = style_action_button(QPushButton("📊 更新进度"), min_w=140)
        self.btn_progress.clicked.connect(lambda: self._act("progress"))
        right.addWidget(self.btn_progress)
        self.btn_edit = style_action_button(QPushButton("📝 编辑查看"), min_w=140)
        self.btn_edit.clicked.connect(lambda: self._act("edit"))
        right.addWidget(self.btn_edit)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_done = style_action_button(QPushButton("✅ 完成"), min_w=88)
        self.btn_done.clicked.connect(lambda: self._act("done"))
        self.btn_abandon = style_action_button(QPushButton("❌ 废弃"), min_w=88)
        self.btn_abandon.setObjectName("btnWarning")
        self.btn_abandon.clicked.connect(lambda: self._act("abandon"))
        row.addWidget(self.btn_done)
        row.addWidget(self.btn_abandon)
        right.addLayout(row)

        right.addStretch()
        btn_close = style_action_button(QPushButton("关闭"), min_w=80)
        btn_close.setObjectName("btnWarning")
        btn_close.clicked.connect(self.reject)
        right.addWidget(btn_close)
        root.addLayout(right, 2)

        self._set_actions_enabled(False)
        self._reload()

    def _toggle_list(self):
        self._list_collapsed = not self._list_collapsed
        self.list_frame.setVisible(not self._list_collapsed)
        self.btn_fold.setText("展开 ▼" if self._list_collapsed else "收起 ▲")

    def _reload(self):
        self.task_list.clear()
        self._tasks = list(self.task_service.get_all_tasks())
        current = self.task_service.get_current_task()
        cur_id = current.id if current else None
        for t in self._tasks:
            star = "★ " if t.id == cur_id else ""
            pct = getattr(t, "progress", 0)
            item = QListWidgetItem(f"{star}{t.title}  ({pct}%)")
            item.setData(Qt.UserRole, t.id)
            item.setToolTip(t.title)
            self.task_list.addItem(item)
        self.lbl_count.setText(f"共 {len(self._tasks)} 项（滚动查看）")
        if self.task_list.count():
            # 优先选中当前轮播任务
            idx = 0
            if cur_id:
                for i in range(self.task_list.count()):
                    if self.task_list.item(i).data(Qt.UserRole) == cur_id:
                        idx = i
                        break
            self.task_list.setCurrentRow(idx)
        else:
            self._on_select(None, None)

    def _task_by_id(self, tid: str):
        for t in self._tasks:
            if t.id == tid:
                return t
        return self.task_service.find_task(tid)

    def _on_select(self, current: QListWidgetItem | None, _prev):
        if not current:
            self.lbl_task.setText("请选择左侧任务")
            self.lbl_meta.setText("")
            self._set_actions_enabled(False)
            return
        tid = current.data(Qt.UserRole)
        t = self._task_by_id(tid)
        if not t:
            self._set_actions_enabled(False)
            return
        self.lbl_task.setText(t.title)
        meta = (
            f"分类: {t.category}　优先级: {t.priority}　"
            f"进度: {getattr(t, 'progress', 0)}%　"
            f"类型: {getattr(t, 'task_type', 'one-time')}"
        )
        if t.deadline:
            meta += f"\n截止: {t.deadline}"
        self.lbl_meta.setText(meta)
        self._set_actions_enabled(True)

    def _set_actions_enabled(self, on: bool):
        for b in (
            self.btn_select,
            self.btn_progress,
            self.btn_edit,
            self.btn_done,
            self.btn_abandon,
        ):
            b.setEnabled(on)

    def _act(self, action: str):
        item = self.task_list.currentItem()
        if not item:
            return
        self.selected_action = (action, item.data(Qt.UserRole))
        self.accept()

    def get_selected_action(self):
        return self.selected_action
