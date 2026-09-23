import os
import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QPushButton, QRadioButton, QWidget, QFileDialog,
    QSlider, QTextBrowser, QCheckBox, QMessageBox, QApplication,
    QTimeEdit, QListWidget, QInputDialog, QSpinBox, QDateEdit,
    QGroupBox, QFormLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QTime, QDate
from zentray.core.models import Task, PeriodicTemplate
from zentray.core.reminder import ReminderSlot, TaskReminder
from zentray.ui.dialog_utils import (
    apply_dialog_chrome,
    center_dialog as _center_dialog,
    fit_dialog,
    style_action_button,
    dialog_root_with_scroll,
)

TITLE_MAX_LENGTH = 100


def _compute_default_deadline() -> datetime.date:
    """一次性任务默认截止日期：明天。"""
    return datetime.date.today() + datetime.timedelta(days=1)


def _date_to_qdate(d: datetime.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _qdate_to_str(qd: QDate) -> str:
    if not qd.isValid():
        return ""
    return f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"


class TaskDialog(QDialog):
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        self.is_editing = task is not None
        self.attachments = list(task.attachments) if isinstance(task, Task) else []

        self.setWindowTitle("修改任务" if self.is_editing else "新建任务")
        apply_dialog_chrome(self, width=820, height=480)

        from zentray.services.settings_manager import SettingsManager

        self._cat_settings = SettingsManager().categories
        self._reminder_slots: list = []

        self.init_ui()
        self.populate_data()
        # 新建任务：保证默认截止日期正确写入（不依赖 radio 信号时序）
        if not self.is_editing:
            self._refresh_default_deadline(force=True)
        _center_dialog(self)

    def init_ui(self):
        _, content, footer = dialog_root_with_scroll(self)
        body = QHBoxLayout(content)
        body.setContentsMargins(4, 4, 8, 4)
        body.setSpacing(16)

        # —— 左栏：模式 / 标题 / 分类 / 截止 / 周期 ——
        left = QVBoxLayout()
        left.setSpacing(10)

        # 1. 任务类型
        self.type_widget = QWidget()
        type_layout = QHBoxLayout(self.type_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.addWidget(QLabel("任务模式:"))

        self.rb_one_time = QRadioButton("一次性任务")
        self.rb_periodic = QRadioButton("周期任务")
        type_layout.addWidget(self.rb_one_time)
        type_layout.addWidget(self.rb_periodic)

        self.period_combo = QComboBox()
        self.period_combo.addItem("每天 (daily)", "daily")
        self.period_combo.addItem("每周 (weekly)", "weekly")
        self.period_combo.addItem("每月 (monthly)", "monthly")
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        self.period_combo.hide()
        type_layout.addWidget(self.period_combo)
        type_layout.addStretch()

        if not self.is_editing:
            left.addWidget(self.type_widget)
        elif isinstance(self.task, PeriodicTemplate):
            left.addWidget(self.type_widget)
            self.rb_periodic.setChecked(True)
            self.rb_one_time.setEnabled(False)
            self.period_combo.show()

        # 2. 标题
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("标题:"))
        self.title_entry = QLineEdit()
        self.title_entry.setPlaceholderText("用一句话描述待办...")
        self.title_entry.setMaxLength(TITLE_MAX_LENGTH)
        self.title_entry.textChanged.connect(self._on_title_changed)
        title_row.addWidget(self.title_entry, 1)
        self.title_counter = QLabel(f"0/{TITLE_MAX_LENGTH}")
        self.title_counter.setStyleSheet("color: #aaa; font-size: 11px;")
        self.title_counter.setMinimumWidth(48)
        title_row.addWidget(self.title_counter)
        left.addLayout(title_row)

        # 3. 分类与优先级（同一行）
        cp_layout = QHBoxLayout()
        cp_layout.addWidget(QLabel("一级:"))
        self.primary_combo = QComboBox()
        for p in self._cat_settings.primary_list:
            self.primary_combo.addItem(p.name, p.id)
        if self.primary_combo.count() == 0:
            self.primary_combo.addItem("工作", "")
        self.primary_combo.currentIndexChanged.connect(self._on_primary_changed)
        self.primary_combo.setMinimumWidth(120)
        cp_layout.addWidget(self.primary_combo, 1)
        self.category_combo = self.primary_combo

        cp_layout.addWidget(QLabel("优先级:"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItem("🔴 紧急高危", "high")
        self.priority_combo.addItem("🟡 中等优先级", "medium")
        self.priority_combo.addItem("🟢 低优先级", "low")
        self.priority_combo.setMinimumWidth(130)
        cp_layout.addWidget(self.priority_combo, 1)
        left.addLayout(cp_layout)

        self.secondary_row = QWidget()
        sec_layout = QHBoxLayout(self.secondary_row)
        sec_layout.setContentsMargins(0, 0, 0, 0)
        sec_layout.addWidget(QLabel("二级:"))
        self.secondary_combo = QComboBox()
        sec_layout.addWidget(self.secondary_combo, 1)
        self.btn_add_secondary = style_action_button(QPushButton("➕ 添加二级"), min_w=100)
        self.btn_add_secondary.clicked.connect(self._add_secondary)
        sec_layout.addWidget(self.btn_add_secondary)
        left.addWidget(self.secondary_row)
        self.secondary_row.setVisible(self._cat_settings.enabled_secondary)
        self._reload_secondaries()

        # 4. 截止 / 周期
        self.one_shot_deadline_box = QGroupBox("截止日期")
        one_dl = QVBoxLayout(self.one_shot_deadline_box)
        dl_check_layout = QHBoxLayout()
        self.cb_deadline = QCheckBox("设置截止日期")
        self.cb_deadline.setChecked(True)
        self.cb_deadline.toggled.connect(self._on_deadline_toggled)
        dl_check_layout.addWidget(self.cb_deadline)
        self.cb_auto_abandon = QCheckBox("逾期自动废弃")
        self.cb_auto_abandon.setToolTip("到期未完成则自动归档废弃")
        dl_check_layout.addWidget(self.cb_auto_abandon)
        dl_check_layout.addStretch()
        one_dl.addLayout(dl_check_layout)

        dl_layout = QHBoxLayout()
        dl_layout.addWidget(QLabel("日期:"))
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setDisplayFormat("yyyy-MM-dd")
        self.deadline_edit.setDate(
            _date_to_qdate(datetime.date.today() + datetime.timedelta(days=1))
        )
        self.deadline_edit.setMinimumDate(QDate(2000, 1, 1))
        dl_layout.addWidget(self.deadline_edit, 1)
        one_dl.addLayout(dl_layout)
        left.addWidget(self.one_shot_deadline_box)

        self.periodic_opts = QGroupBox("周期调度")
        po = QVBoxLayout(self.periodic_opts)

        row_iv = QHBoxLayout()
        row_iv.addWidget(QLabel("间隔: 每"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 365)
        self.interval_spin.setValue(1)
        row_iv.addWidget(self.interval_spin)
        self.interval_unit_label = QLabel("天")
        row_iv.addWidget(self.interval_unit_label)
        row_iv.addStretch()
        po.addLayout(row_iv)

        row_rule = QHBoxLayout()
        row_rule.addWidget(QLabel("实例截止:"))
        self.deadline_weekday = QComboBox()
        for i, name in enumerate(["周一", "周二", "周三", "周四", "周五", "周六", "周日"]):
            self.deadline_weekday.addItem(name, i)
        self.deadline_weekday.setCurrentIndex(4)
        row_rule.addWidget(self.deadline_weekday)
        self.deadline_dom = QSpinBox()
        self.deadline_dom.setRange(1, 31)
        self.deadline_dom.setValue(25)
        self.deadline_dom.setPrefix("每月 ")
        self.deadline_dom.setSuffix(" 日")
        row_rule.addWidget(self.deadline_dom)
        self.cb_tmpl_auto_abandon = QCheckBox("逾期废弃")
        row_rule.addWidget(self.cb_tmpl_auto_abandon)
        row_rule.addStretch()
        po.addLayout(row_rule)

        row_life = QHBoxLayout()
        self.cb_long_term = QCheckBox("长期有效")
        self.cb_long_term.setChecked(True)
        self.cb_long_term.toggled.connect(self._on_long_term_toggled)
        row_life.addWidget(self.cb_long_term)
        row_life.addWidget(QLabel("停止日:"))
        self.schedule_end_entry = QLineEdit()
        self.schedule_end_entry.setPlaceholderText("YYYY-MM-DD")
        self.schedule_end_entry.setEnabled(False)
        row_life.addWidget(self.schedule_end_entry, 1)
        po.addLayout(row_life)

        self.periodic_opts.hide()
        left.addWidget(self.periodic_opts)
        left.addStretch(1)
        body.addLayout(left, 3)

        # —— 右栏：详情 / 附件 / 提醒 ——
        right = QVBoxLayout()
        right.setSpacing(10)

        right.addWidget(QLabel("任务详情 (选填):"))
        self.details_edit = QTextEdit()
        self.details_edit.setPlaceholderText("补充说明…")
        self.details_edit.setMinimumHeight(80)
        self.details_edit.setMaximumHeight(140)
        right.addWidget(self.details_edit)

        att_box = QGroupBox("附件")
        att_l = QVBoxLayout(att_box)
        att_row = QHBoxLayout()
        btn_add_att = style_action_button(QPushButton("➕ 选取文件"), min_w=100)
        btn_add_att.clicked.connect(self.add_attachment)
        att_row.addWidget(btn_add_att)
        att_row.addStretch()
        att_l.addLayout(att_row)
        self.att_list_label = QLabel("暂未附加任何文件")
        self.att_list_label.setStyleSheet("color: #888;")
        self.att_list_label.setWordWrap(True)
        att_l.addWidget(self.att_list_label)
        right.addWidget(att_box)

        rem_box = QGroupBox("弹窗提醒")
        rem_l = QVBoxLayout(rem_box)
        rem_row = QHBoxLayout()
        self.cb_reminder = QCheckBox("启用提醒")
        self.cb_reminder.toggled.connect(self._on_reminder_toggled)
        rem_row.addWidget(self.cb_reminder)
        rem_row.addWidget(QLabel("默认时间:"))
        self.reminder_time = QTimeEdit()
        self.reminder_time.setDisplayFormat("HH:mm")
        self.reminder_time.setTime(QTime(17, 0))
        rem_row.addWidget(self.reminder_time)
        rem_row.addStretch()
        rem_l.addLayout(rem_row)

        self.slots_widget = QWidget()
        slots_layout = QVBoxLayout(self.slots_widget)
        slots_layout.setContentsMargins(0, 0, 0, 0)
        slots_hint = QLabel("周/月多提醒点：")
        slots_hint.setStyleSheet("color: #888; font-size: 11px;")
        slots_layout.addWidget(slots_hint)
        self.slots_list = QListWidget()
        self.slots_list.setMaximumHeight(72)
        slots_layout.addWidget(self.slots_list)
        slot_btns = QHBoxLayout()
        btn_add_slot = style_action_button(QPushButton("添加提醒点"), min_w=96)
        btn_add_slot.clicked.connect(self._add_reminder_slot)
        btn_rm_slot = style_action_button(QPushButton("删除选中"), min_w=88)
        btn_rm_slot.clicked.connect(self._remove_reminder_slot)
        slot_btns.addWidget(btn_add_slot)
        slot_btns.addWidget(btn_rm_slot)
        slot_btns.addStretch()
        slots_layout.addLayout(slot_btns)
        rem_l.addWidget(self.slots_widget)
        right.addWidget(rem_box)

        self.slots_widget.setVisible(False)
        self.cb_reminder.setChecked(False)
        self.reminder_time.setEnabled(False)
        right.addStretch(1)
        body.addLayout(right, 2)

        # 底部按钮（始终可见）
        footer.addStretch()
        btn_cancel = style_action_button(QPushButton("取消"), min_w=88)
        btn_cancel.setObjectName("btnWarning")
        btn_cancel.clicked.connect(self.reject)
        self.btn_save = style_action_button(QPushButton("💾 保存任务"), min_w=120)
        self.btn_save.clicked.connect(self._validate_and_accept)
        footer.addWidget(btn_cancel)
        footer.addWidget(self.btn_save)

        self.rb_periodic.toggled.connect(self._on_type_toggled)
        self.period_combo.currentTextChanged.connect(self._update_slots_visibility)
        self.rb_one_time.setChecked(True)

    def _on_title_changed(self, text: str):
        self.title_counter.setText(f"{len(text)}/{TITLE_MAX_LENGTH}")

    def _on_primary_changed(self, _idx: int = 0):
        self._reload_secondaries()

    def _reload_secondaries(self):
        self.secondary_combo.clear()
        self.secondary_combo.addItem("（无）", None)
        pid = self.primary_combo.currentData()
        primary = self._cat_settings.find_primary(pid)
        if primary:
            for s in primary.secondaries:
                self.secondary_combo.addItem(s.name, s.id)

    def _add_secondary(self):
        """任务页可添加二级（不可添加一级）。"""
        from zentray.services.settings_manager import SettingsManager

        pid = self.primary_combo.currentData()
        primary = self._cat_settings.find_primary(pid)
        if not primary:
            QMessageBox.warning(self, "无法添加", "请先选择有效的一级分类。")
            return
        name, ok = QInputDialog.getText(self, "添加二级分类", "二级分类名称:")
        if not ok or not name.strip():
            return
        sec = primary.add_secondary(name.strip())
        # 持久化分类库
        sm = SettingsManager()
        sm.categories.primary_list = self._cat_settings.primary_list
        sm.save()
        self._cat_settings = sm.categories
        self._reload_secondaries()
        idx = self.secondary_combo.findData(sec.id)
        if idx >= 0:
            self.secondary_combo.setCurrentIndex(idx)

    def _on_reminder_toggled(self, checked: bool):
        self.reminder_time.setEnabled(checked)
        self._update_slots_visibility()

    def _update_slots_visibility(self):
        p = self._current_periodicity()
        show_slots = (
            self.cb_reminder.isChecked()
            and self.rb_periodic.isChecked()
            and p in ("weekly", "monthly")
        )
        self.slots_widget.setVisible(show_slots)

    def _add_reminder_slot(self):
        periodicity = self._current_periodicity()
        t = self.reminder_time.time()
        time_str = f"{t.hour():02d}:{t.minute():02d}"
        if periodicity == "weekly":
            day, ok = QInputDialog.getInt(
                self, "周几", "0=周一 … 6=周日", 0, 0, 6, 1
            )
            if not ok:
                return
            slot = ReminderSlot(time_of_day=time_str, weekday=day)
            label = f"周{day} {time_str}"
        else:
            day, ok = QInputDialog.getInt(
                self, "每月几号", "日期 1-31", 1, 1, 31, 1
            )
            if not ok:
                return
            slot = ReminderSlot(time_of_day=time_str, day_of_month=day)
            label = f"每月{day}日 {time_str}"
        self._reminder_slots.append(slot)
        self.slots_list.addItem(label)

    def _remove_reminder_slot(self):
        row = self.slots_list.currentRow()
        if row < 0:
            return
        self.slots_list.takeItem(row)
        if 0 <= row < len(self._reminder_slots):
            self._reminder_slots.pop(row)

    def _on_type_toggled(self):
        is_p = self.rb_periodic.isChecked()
        if is_p:
            self.period_combo.show()
            self.periodic_opts.show()
            self.one_shot_deadline_box.hide()
        else:
            self.period_combo.hide()
            self.periodic_opts.hide()
            self.one_shot_deadline_box.show()
        self._refresh_period_unit_label()
        self._refresh_deadline_rule_visibility()
        self._refresh_default_deadline()
        self._update_slots_visibility()

    def _on_period_changed(self, _idx: int = 0):
        self._refresh_period_unit_label()
        self._refresh_deadline_rule_visibility()
        if self.rb_periodic.isChecked():
            self._refresh_default_deadline()
        self._update_slots_visibility()

    def _refresh_period_unit_label(self):
        p = self.period_combo.currentData() or "daily"
        self.interval_unit_label.setText(
            {"daily": "天", "weekly": "周", "monthly": "月"}.get(p, "天")
        )

    def _refresh_deadline_rule_visibility(self):
        p = self.period_combo.currentData() or "daily"
        self.deadline_weekday.setVisible(p == "weekly")
        self.deadline_dom.setVisible(p == "monthly")
        # daily 无额外规则控件

    def _on_long_term_toggled(self, checked: bool):
        self.schedule_end_entry.setEnabled(not checked)

    def _current_periodicity(self) -> str:
        return self.period_combo.currentData() or "daily"

    def _on_deadline_toggled(self, checked: bool):
        self.deadline_edit.setEnabled(checked)
        if checked:
            self._refresh_default_deadline(force=True)
        else:
            self.deadline_edit.setSpecialValueText("无截止日期")

    def _refresh_default_deadline(self, force: bool = False):
        """刷新一次性任务默认截止日期：新建默认为「明天」。"""
        if not hasattr(self, "deadline_edit"):
            return
        # 周期模板编辑不使用日期框
        if isinstance(self.task, PeriodicTemplate):
            return
        if self.rb_periodic.isChecked() and not self.is_editing:
            return
        if self.is_editing and isinstance(self.task, Task) and not force:
            return
        if not self.cb_deadline.isChecked() and not force:
            return

        default = _compute_default_deadline()
        self.deadline_edit.setDate(_date_to_qdate(default))
        self.deadline_edit.setToolTip(f"默认截止日期: {default.isoformat()}")
        self.deadline_edit.setEnabled(self.cb_deadline.isChecked())

    def _validate_and_accept(self):
        """保存前校验"""
        title = self.title_entry.text().strip()
        if not title:
            QMessageBox.warning(self, "标题不能为空", "请输入任务标题。")
            self.title_entry.setFocus()
            return
        if len(title) > TITLE_MAX_LENGTH:
            QMessageBox.warning(self, "标题过长", f"标题最多 {TITLE_MAX_LENGTH} 个字符。")
            self.title_entry.setFocus()
            return
        self.accept()

    def add_attachment(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择你要附加的文件")
        if file_path and file_path not in self.attachments:
            self.attachments.append(file_path)
            self.update_att_label()

    def update_att_label(self):
        if not self.attachments:
            self.att_list_label.setText("暂未附加任何文件")
        else:
            names = [os.path.basename(p) for p in self.attachments]
            self.att_list_label.setText("📦 " + ", ".join(names))

    def _apply_category_selection(self, primary_id, secondary_id, category_name):
        if primary_id:
            idx = self.primary_combo.findData(primary_id)
            if idx >= 0:
                self.primary_combo.setCurrentIndex(idx)
        else:
            idx = self.primary_combo.findText(category_name or "")
            if idx >= 0:
                self.primary_combo.setCurrentIndex(idx)
        self._reload_secondaries()
        if secondary_id:
            sidx = self.secondary_combo.findData(secondary_id)
            if sidx >= 0:
                self.secondary_combo.setCurrentIndex(sidx)

    def _apply_reminder_ui(self, reminder: TaskReminder | None):
        if not reminder or not reminder.enabled:
            self.cb_reminder.setChecked(False)
            return
        self.cb_reminder.setChecked(True)
        h, m = 17, 0
        try:
            parts = (reminder.time_of_day or "17:00").split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            pass
        self.reminder_time.setTime(QTime(h, m))
        self._reminder_slots = list(reminder.slots or [])
        self.slots_list.clear()
        for s in self._reminder_slots:
            if s.weekday is not None:
                self.slots_list.addItem(f"周{s.weekday} {s.time_of_day}")
            elif s.day_of_month is not None:
                self.slots_list.addItem(f"每月{s.day_of_month}日 {s.time_of_day}")
            else:
                self.slots_list.addItem(s.time_of_day)
        self._update_slots_visibility()

    def populate_data(self):
        if not self.task:
            return
        if isinstance(self.task, Task):
            self.title_entry.setText(self.task.title)
            self._on_title_changed(self.task.title)
            self._apply_category_selection(
                getattr(self.task, "category_primary_id", None),
                getattr(self.task, "category_secondary_id", None),
                self.task.category,
            )
            idx = self.priority_combo.findData(self.task.priority)
            if idx >= 0:
                self.priority_combo.setCurrentIndex(idx)
            has_deadline = bool(self.task.deadline)
            self.cb_deadline.setChecked(has_deadline)
            if has_deadline:
                try:
                    d = datetime.date.fromisoformat(self.task.deadline)
                    self.deadline_edit.setDate(_date_to_qdate(d))
                except ValueError:
                    self.deadline_edit.setDate(
                        _date_to_qdate(datetime.date.today() + datetime.timedelta(days=1))
                    )
            self.deadline_edit.setEnabled(has_deadline)
            self.details_edit.setPlainText(self.task.details)
            self.update_att_label()
            self._apply_reminder_ui(getattr(self.task, "reminder", None))
            self.cb_auto_abandon.setChecked(
                bool(getattr(self.task, "auto_abandon_on_overdue", False))
            )
            # 周期实例可像一次性任务一样编辑
            self.one_shot_deadline_box.show()
            self.periodic_opts.hide()
        elif isinstance(self.task, PeriodicTemplate):
            self.title_entry.setText(self.task.base_title)
            self._on_title_changed(self.task.base_title)
            self._apply_category_selection(
                getattr(self.task, "category_primary_id", None),
                getattr(self.task, "category_secondary_id", None),
                self.task.category,
            )
            idx = self.priority_combo.findData(self.task.priority)
            if idx >= 0:
                self.priority_combo.setCurrentIndex(idx)
            self.details_edit.setPlainText(self.task.details)
            pidx = self.period_combo.findData(self.task.periodicity)
            if pidx >= 0:
                self.period_combo.setCurrentIndex(pidx)
            self.interval_spin.setValue(max(1, int(getattr(self.task, "interval", 1) or 1)))
            if getattr(self.task, "deadline_weekday", None) is not None:
                self.deadline_weekday.setCurrentIndex(int(self.task.deadline_weekday) % 7)
            if getattr(self.task, "deadline_day_of_month", None) is not None:
                self.deadline_dom.setValue(int(self.task.deadline_day_of_month))
            self.cb_tmpl_auto_abandon.setChecked(
                bool(getattr(self.task, "auto_abandon_on_overdue", False))
            )
            lt = bool(getattr(self.task, "long_term", True))
            self.cb_long_term.setChecked(lt)
            self.schedule_end_entry.setText(getattr(self.task, "schedule_end_date", None) or "")
            self.schedule_end_entry.setEnabled(not lt)
            self.att_list_label.setText("周期模板不支持附件")
            self._apply_reminder_ui(getattr(self.task, "reminder", None))
            self.rb_periodic.setChecked(True)
            self._on_type_toggled()

    def get_data(self) -> dict:
        editing_template = self.is_editing and isinstance(self.task, PeriodicTemplate)
        is_periodic = (
            self.rb_periodic.isChecked()
            if not self.is_editing
            else editing_template
        )
        deadline = ""
        if self.is_editing and isinstance(self.task, Task):
            is_periodic = False
            if self.cb_deadline.isChecked():
                deadline = _qdate_to_str(self.deadline_edit.date())
        elif not is_periodic and self.cb_deadline.isChecked():
            deadline = _qdate_to_str(self.deadline_edit.date())

        t = self.reminder_time.time()
        time_str = f"{t.hour():02d}:{t.minute():02d}"
        if self.cb_reminder.isChecked():
            reminder = TaskReminder(
                enabled=True,
                time_of_day=time_str,
                slots=list(self._reminder_slots),
            ).to_dict()
        else:
            reminder = TaskReminder(enabled=False).to_dict()

        data = {
            "title": self.title_entry.text().strip(),
            "category": self.primary_combo.currentText(),
            "category_primary_id": self.primary_combo.currentData(),
            "category_secondary_id": self.secondary_combo.currentData(),
            "priority": self.priority_combo.currentData(),
            "deadline": deadline,
            "details": self.details_edit.toPlainText().strip(),
            "attachments": self.attachments if not is_periodic else [],
            "task_type": "periodic" if is_periodic else (
                getattr(self.task, "task_type", "one-time")
                if isinstance(self.task, Task)
                else "one-time"
            ),
            "reminder": reminder,
            "auto_abandon_on_overdue": (
                self.cb_tmpl_auto_abandon.isChecked()
                if is_periodic
                else self.cb_auto_abandon.isChecked()
            ),
        }
        if is_periodic:
            data["periodicity"] = self._current_periodicity()
            data["interval"] = self.interval_spin.value()
            data["long_term"] = self.cb_long_term.isChecked()
            data["schedule_end_date"] = (
                None
                if self.cb_long_term.isChecked()
                else (self.schedule_end_entry.text().strip() or None)
            )
            p = data["periodicity"]
            data["deadline_weekday"] = (
                self.deadline_weekday.currentData() if p == "weekly" else None
            )
            data["deadline_day_of_month"] = (
                self.deadline_dom.value() if p == "monthly" else None
            )
        return data

class ProgressDialog(QDialog):
    """更新进度；可保存 / 完成 / 废弃。result_action: save | done | abandon

    进度仅支持 10% 步进；渐变填充条与拖拽手柄合一。
    横版：左侧历史，右侧进度与操作。
    """

    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        self.result_action = "save"
        title = (task.title if task else "") or ""
        short = title if len(title) <= 28 else title[:25] + "…"
        self.setWindowTitle(f"更新进度 · {short}" if short else "更新进度")
        apply_dialog_chrome(self, width=720, height=380)
        self.init_ui()
        _center_dialog(self)

    def init_ui(self):
        from zentray.ui.progress_slider import GradientProgressSlider, snap_progress_10

        _, content, footer = dialog_root_with_scroll(self, margins=(16, 14, 16, 12))
        body = QHBoxLayout(content)
        body.setContentsMargins(4, 4, 4, 4)
        body.setSpacing(16)

        # 左：历史
        left = QVBoxLayout()
        left.addWidget(QLabel("历史进展记录:"))
        self.history_display = QTextBrowser()
        self.history_display.setMinimumHeight(120)
        logs = getattr(self.task, "progress_logs", [])
        if not logs:
            self.history_display.setPlainText("暂无历史进展记录。")
        else:
            log_texts = []
            for log in logs:
                t = log.get("time", "")
                p = log.get("percent", 0)
                n = log.get("note", "")
                log_texts.append(f"📅 {t} | 进度: {p}% \n   备注: {n if n else '无'}")
            self.history_display.setPlainText("\n\n".join(log_texts))
        left.addWidget(self.history_display, 1)
        body.addLayout(left, 1)

        # 右：进度 + 备注 + 完成/废弃
        right = QVBoxLayout()
        right.setSpacing(10)

        pct_row = QHBoxLayout()
        pct_row.addWidget(QLabel("当前进度（拖动，每格 10%）:"))
        self.slider_val_label = QLabel("0%")
        self.slider_val_label.setMinimumWidth(48)
        self.slider_val_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        pct_row.addStretch()
        pct_row.addWidget(self.slider_val_label)
        right.addLayout(pct_row)

        current_pct = snap_progress_10(getattr(self.task, "progress", 0))
        self.slider = GradientProgressSlider(self, value=current_pct)
        self.slider.valueChanged.connect(self.on_slider_changed)
        right.addWidget(self.slider)
        self.on_slider_changed(current_pct)

        hint = QLabel("提示：鼠标拖动 / 滚轮 / ←→ 键，进度仅以 10% 为单位。")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        right.addWidget(hint)

        right.addWidget(QLabel("本次进展描述 (选填):"))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("记录一下当前做完的事情吧...")
        right.addWidget(self.note_edit)

        act_row = QHBoxLayout()
        btn_done = style_action_button(QPushButton("✅ 完成任务"), min_w=110)
        btn_done.clicked.connect(self._on_done)
        btn_abandon = style_action_button(QPushButton("❌ 废弃任务"), min_w=110)
        btn_abandon.setObjectName("btnWarning")
        btn_abandon.clicked.connect(self._on_abandon)
        act_row.addWidget(btn_done)
        act_row.addWidget(btn_abandon)
        right.addLayout(act_row)
        right.addStretch(1)
        body.addLayout(right, 1)

        footer.addStretch()
        btn_cancel = style_action_button(QPushButton("取消"), min_w=88)
        btn_cancel.setObjectName("btnWarning")
        btn_cancel.clicked.connect(self.reject)
        btn_save = style_action_button(QPushButton("💾 保存进度"), min_w=120)
        btn_save.clicked.connect(self._on_save)
        footer.addWidget(btn_cancel)
        footer.addWidget(btn_save)

    def on_slider_changed(self, val: int):
        from zentray.ui.progress_slider import snap_progress_10

        val = snap_progress_10(val)
        self.slider_val_label.setText(f"{val}%")

    def _on_save(self):
        self.result_action = "save"
        self.accept()

    def _on_done(self):
        self.result_action = "done"
        self.slider.setValue(100)
        self.accept()

    def _on_abandon(self):
        self.result_action = "abandon"
        self.accept()

    def get_data(self) -> tuple:
        from zentray.ui.progress_slider import snap_progress_10

        percent = snap_progress_10(self.slider.value())
        note = self.note_edit.text().strip()
        return percent, note

class TaskActionDialog(QDialog):
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        self.selected_action = None
        self.setWindowTitle("选择操作")
        apply_dialog_chrome(self, width=520, height=240)
        self.init_ui()
        _center_dialog(self)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        title_label = QLabel(f"<b>当前任务：</b> {self.task.title}")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(title_label)

        # 横排操作按钮
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        btn_select = style_action_button(QPushButton("🔄 切换到此任务"), min_w=130)
        btn_select.clicked.connect(lambda: self.trigger_action("select"))
        btn_progress = style_action_button(QPushButton("📊 更新任务进度"), min_w=130)
        btn_progress.clicked.connect(lambda: self.trigger_action("progress"))
        btn_edit = style_action_button(QPushButton("📝 编辑任务详情"), min_w=130)
        btn_edit.clicked.connect(lambda: self.trigger_action("edit"))
        row1.addWidget(btn_select)
        row1.addWidget(btn_progress)
        row1.addWidget(btn_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        btn_done = style_action_button(QPushButton("✅ 完成"), min_w=100)
        btn_done.clicked.connect(lambda: self.trigger_action("done"))
        btn_abandon = style_action_button(QPushButton("❌ 废弃"), min_w=100)
        btn_abandon.setObjectName("btnWarning")
        btn_abandon.clicked.connect(lambda: self.trigger_action("abandon"))
        btn_cancel = style_action_button(QPushButton("取消"), min_w=88)
        btn_cancel.setObjectName("btnWarning")
        btn_cancel.clicked.connect(self.reject)
        row2.addWidget(btn_done)
        row2.addWidget(btn_abandon)
        row2.addStretch()
        row2.addWidget(btn_cancel)
        layout.addLayout(row2)

    def trigger_action(self, action):
        self.selected_action = action
        self.accept()

    def get_selected_action(self):
        return self.selected_action
