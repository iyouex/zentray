# zentray/ui/settings_dialog.py
"""
设置对话框 —— 左侧导航 + 右侧堆叠页面。

校验规则：高优停留 ≥ 中优停留 ≥ 低优停留（强要求）。
"""
import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QSpinBox, QCheckBox, QComboBox,
    QMessageBox, QGroupBox, QFormLayout, QListWidget,
    QListWidgetItem, QStackedWidget, QTextEdit,
    QInputDialog, QSplitter, QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import uuid

from zentray.core.categories import (
    WRAP_PRESETS,
    CategorySettings,
    PrimaryCategory,
    default_category_settings,
)
from zentray.services.ai_styles import (
    AIStyle,
    STYLE_TOXIC,
    default_system_prompt,
    merge_styles,
)
from zentray.services.settings_manager import SettingsManager, AppSettings
from zentray.services.system_utils import (
    is_shortcut_created, is_autostart_enabled,
    toggle_shortcut, toggle_autostart, APP_NAME,
)

# 侧栏导航：文案可完整显示；宽度由 Splitter 拖拽，受 min/max 限制
NAV_ITEMS = [
    ("🤖 AI教练 & 通知", 0),
    ("📁 分类", 1),
    ("📋 任务轮播", 2),
    ("🍅 番茄钟", 3),
    ("🎨 外观", 4),
    ("💻 系统", 5),
]

NAV_MIN_WIDTH = 120
NAV_MAX_WIDTH = 280
NAV_DEFAULT_WIDTH = 168
DIALOG_MIN_W = 720
DIALOG_MIN_H = 520


class SettingsDialog(QDialog):
    """应用设置对话框 —— 左侧导航 + 右侧设置页（横版）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ZenTray 设置")
        from zentray.ui.dialog_utils import apply_dialog_chrome, style_action_button

        self._style_action_button = style_action_button
        apply_dialog_chrome(self, width=900, height=560)

        self._manager = SettingsManager()
        self._settings = self._manager.get_all()

        # 系统设置变更追踪
        self._shortcut_changed = False
        self._autostart_changed = False

        self.init_ui()
        self._load_values()

    # ==========================================
    # UI 构建
    # ==========================================

    def _wrap_scroll(self, page: QWidget) -> QScrollArea:
        """右侧详情页可滚动，避免内容挤压。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        page.setMinimumWidth(360)
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        scroll.setWidget(page)
        return scroll

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 标题
        title = QLabel("⚙️ 应用设置")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        # 主体：可拖拽分隔的左侧导航 + 右侧滚动详情
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)

        # 左侧导航（宽度自适应可拖，有上下限）
        self.nav_list = QListWidget()
        self.nav_list.setMinimumWidth(NAV_MIN_WIDTH)
        self.nav_list.setMaximumWidth(NAV_MAX_WIDTH)
        self.nav_list.setSpacing(2)
        self.nav_list.setWordWrap(True)
        self.nav_list.setTextElideMode(Qt.ElideNone)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                background: #f8fafc;
                padding: 6px 4px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 10px;
                border-radius: 6px;
                font-size: 13px;
                color: #334155;
            }
            QListWidget::item:selected {
                background: #dbeafe;
                color: #1e3a5f;
                font-weight: bold;
            }
            QListWidget::item:hover:!selected {
                background: #eef2f7;
                color: #0f172a;
            }
        """)
        for label, idx in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, idx)
            item.setToolTip(label)
            self.nav_list.addItem(item)
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        self.splitter.addWidget(self.nav_list)

        # 右侧堆叠 + 各页独立滚动
        self.stack = QStackedWidget()
        self.stack.addWidget(self._wrap_scroll(self._create_ai_notification_page()))  # 0
        self.stack.addWidget(self._wrap_scroll(self._create_categories_page()))       # 1
        self.stack.addWidget(self._wrap_scroll(self._create_polling_page()))          # 2
        self.stack.addWidget(self._wrap_scroll(self._create_pomodoro_page()))         # 3
        self.stack.addWidget(self._wrap_scroll(self._create_appearance_page()))       # 4
        self.stack.addWidget(self._wrap_scroll(self._create_system_page()))           # 5
        self.stack.setCurrentIndex(0)
        self.splitter.addWidget(self.stack)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([NAV_DEFAULT_WIDTH, 640])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        layout.addWidget(self.splitter, 1)

        # 底部按钮（最小宽度保证文字完整）
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        btn_cancel = self._style_action_button(QPushButton("取消"), min_w=88)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = self._style_action_button(QPushButton("💾 保存设置"), min_w=120)
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save_and_accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _on_nav_changed(self, row: int):
        item = self.nav_list.item(row)
        if item:
            idx = item.data(Qt.UserRole)
            self.stack.setCurrentIndex(idx)

    def _on_splitter_moved(self, pos: int, index: int):
        """限制侧栏宽度不超过 NAV_MAX_WIDTH。"""
        sizes = self.splitter.sizes()
        if not sizes:
            return
        left = sizes[0]
        if left > NAV_MAX_WIDTH:
            right = sum(sizes) - NAV_MAX_WIDTH
            self.splitter.setSizes([NAV_MAX_WIDTH, max(right, 200)])
        elif left < NAV_MIN_WIDTH:
            right = sum(sizes) - NAV_MIN_WIDTH
            self.splitter.setSizes([NAV_MIN_WIDTH, max(right, 200)])

    # ==========================================
    # AI教练 & 通知页（合并）
    # ==========================================

    def _create_ai_notification_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("🤖 AI 教练 & 消息推送")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        # --- AI 教练 ---
        self.ai_enabled = QCheckBox("启用 AI 每日复盘教练")
        self.ai_enabled.toggled.connect(self._on_ai_toggled)
        layout.addWidget(self.ai_enabled)

        ai_group = QGroupBox("API 配置")
        self.ai_group = ai_group
        form = QFormLayout(ai_group)
        form.setSpacing(8)

        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setPlaceholderText("sk-xxxxxxxxxxxxxxxxxxxxxxxx")
        form.addRow("API Key:", self.ai_key)

        self.ai_base = QLineEdit()
        self.ai_base.setPlaceholderText("https://api.openai.com/v1")
        form.addRow("Base URL:", self.ai_base)

        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText("gpt-4o")
        form.addRow("模型名称:", self.ai_model)

        layout.addWidget(ai_group)

        # AI 风格
        style_group = QGroupBox("教练风格")
        style_layout = QVBoxLayout(style_group)
        row = QHBoxLayout()
        row.addWidget(QLabel("当前风格:"))
        self.ai_style_combo = QComboBox()
        self.ai_style_combo.currentIndexChanged.connect(self._on_style_selected)
        row.addWidget(self.ai_style_combo, 1)
        btn_new_style = QPushButton("新建自定义")
        btn_new_style.clicked.connect(self._add_custom_style)
        row.addWidget(btn_new_style)
        btn_del_style = QPushButton("删除")
        btn_del_style.clicked.connect(self._delete_custom_style)
        row.addWidget(btn_del_style)
        style_layout.addLayout(row)

        style_layout.addWidget(QLabel("系统提示词（可编辑）:"))
        self.ai_style_prompt = QTextEdit()
        self.ai_style_prompt.setMaximumHeight(100)
        style_layout.addWidget(self.ai_style_prompt)

        btn_reset = QPushButton("恢复此预设默认文案")
        btn_reset.clicked.connect(self._reset_builtin_prompt)
        style_layout.addWidget(btn_reset)
        layout.addWidget(style_group)
        self._styles_working: list = []
        self._style_prev_id: str | None = None

        # 复盘时间
        time_group = QGroupBox("自动复盘调度")
        time_layout = QVBoxLayout(time_group)
        row_t = QHBoxLayout()
        row_t.addWidget(QLabel("每天"))
        self.nightly_hour = QSpinBox()
        self.nightly_hour.setRange(0, 23)
        self.nightly_hour.setValue(23)
        self.nightly_hour.setSuffix(" 时")
        row_t.addWidget(self.nightly_hour)
        self.nightly_minute = QSpinBox()
        self.nightly_minute.setRange(0, 59)
        self.nightly_minute.setValue(30)
        self.nightly_minute.setSuffix(" 分")
        self.nightly_minute.setSingleStep(5)
        row_t.addWidget(self.nightly_minute)
        row_t.addStretch()
        time_layout.addLayout(row_t)

        self.cb_skip_weekends = QCheckBox("周六日不自动触发")
        self.cb_skip_weekends.setToolTip("仅影响定时调度；托盘「立即 AI 复盘」仍可手动运行")
        time_layout.addWidget(self.cb_skip_weekends)
        self.cb_skip_holidays = QCheckBox("法定节假日不自动触发")
        self.cb_skip_holidays.setToolTip(
            "使用内置中国法定节假日表，可在数据目录 holidays.json 追加日期"
        )
        time_layout.addWidget(self.cb_skip_holidays)

        hint_review = QLabel(
            "提示：托盘菜单可点「🤖 立即 AI 复盘」随时生成（不受每天一次 / 周末节假日限制）。"
        )
        hint_review.setWordWrap(True)
        hint_review.setStyleSheet("color: #888; font-size: 11px;")
        time_layout.addWidget(hint_review)
        layout.addWidget(time_group)

        # --- 分隔 ---
        sep = QLabel("")
        sep.setFixedHeight(8)
        layout.addWidget(sep)

        # --- 消息推送（依赖 AI） ---
        self.notif_enabled = QCheckBox("启用移动端消息推送")
        self.notif_enabled.toggled.connect(self._toggle_notif_group)
        layout.addWidget(self.notif_enabled)

        notif_group = QGroupBox("WxPusher 凭据")
        self.notif_group = notif_group
        nf = QFormLayout(notif_group)
        nf.setSpacing(8)

        self.wx_token = QLineEdit()
        self.wx_token.setPlaceholderText("AT_xxxxxxxxxxxxxxxxxxxx")
        nf.addRow("App Token:", self.wx_token)

        self.wx_uid = QLineEdit()
        self.wx_uid.setPlaceholderText("UID_xxxxxxxxxxxxxxxxxxxx")
        nf.addRow("UID:", self.wx_uid)

        layout.addWidget(notif_group)

        hint = QLabel("AI 教练启用后需配合消息推送才能接收日报。注册地址: wxpusher.zjiecode.com")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()
        return page

    def _on_ai_toggled(self, checked: bool):
        self.ai_group.setEnabled(checked)
        if checked:
            self.notif_enabled.setChecked(True)

    def _toggle_notif_group(self, checked):
        self.notif_group.setEnabled(checked)

    def _reload_style_combo(self, select_id: str | None = None):
        self.ai_style_combo.blockSignals(True)
        self.ai_style_combo.clear()
        for s in self._styles_working:
            self.ai_style_combo.addItem(s.name, s.id)
        self.ai_style_combo.blockSignals(False)
        if select_id:
            idx = self.ai_style_combo.findData(select_id)
            if idx >= 0:
                self.ai_style_combo.setCurrentIndex(idx)
        self._on_style_selected()

    def _current_style(self) -> AIStyle | None:
        sid = self.ai_style_combo.currentData()
        for s in self._styles_working:
            if s.id == sid:
                return s
        return None

    def _on_style_selected(self, _idx: int = 0):
        # 先把编辑区写回「上一选中」风格
        if self._style_prev_id:
            for s in self._styles_working:
                if s.id == self._style_prev_id:
                    s.system_prompt = self.ai_style_prompt.toPlainText().strip()
                    break
        s = self._current_style()
        self._style_prev_id = s.id if s else None
        if s:
            self.ai_style_prompt.setPlainText(s.system_prompt)
        else:
            self.ai_style_prompt.clear()

    def _flush_style_prompt_to_working(self):
        s = self._current_style()
        if s is not None:
            s.system_prompt = self.ai_style_prompt.toPlainText().strip()
            self._style_prev_id = s.id

    def _add_custom_style(self):
        name, ok = QInputDialog.getText(self, "新建风格", "风格名称:")
        if not ok or not name.strip():
            return
        self._flush_style_prompt_to_working()
        style = AIStyle(
            id=str(uuid.uuid4()),
            name=name.strip(),
            system_prompt="你是一位效率教练。请用 Markdown 输出每日复盘。",
            is_builtin=False,
        )
        self._styles_working.append(style)
        self._reload_style_combo(style.id)

    def _delete_custom_style(self):
        s = self._current_style()
        if not s:
            return
        if s.is_builtin:
            QMessageBox.information(self, "无法删除", "内置风格不能删除，可编辑提示词或恢复默认。")
            return
        self._styles_working = [x for x in self._styles_working if x.id != s.id]
        self._reload_style_combo(STYLE_TOXIC)

    def _reset_builtin_prompt(self):
        s = self._current_style()
        if not s or not s.is_builtin:
            QMessageBox.information(self, "提示", "仅内置风格可恢复默认文案。")
            return
        prompt = default_system_prompt(s.id)
        if prompt:
            s.system_prompt = prompt
            self.ai_style_prompt.setPlainText(prompt)

    # ==========================================
    # 分类页
    # ==========================================

    def _create_categories_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        header = QLabel("📁 任务分类")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        self.cb_sec_enabled = QCheckBox("启用二级分类")
        layout.addWidget(self.cb_sec_enabled)

        # 格式：[一级-二级] — 仅括号样式 + 分隔符
        form = QFormLayout()
        self.wrap_preset = QComboBox()
        for label, left_c, right_c in WRAP_PRESETS:
            self.wrap_preset.addItem(label, (left_c, right_c))
        self.wrap_preset.currentIndexChanged.connect(self._on_wrap_preset)
        form.addRow("括号样式:", self.wrap_preset)
        self.level_sep = QLineEdit("-")
        self.level_sep.setMaximumWidth(80)
        self.level_sep.setPlaceholderText("如 - 或 /")
        form.addRow("一二级分隔符:", self.level_sep)
        layout.addLayout(form)

        preview = QLabel("标题预览: [工作-需求] 示例任务")
        preview.setObjectName("catPreview")
        preview.setStyleSheet("color: #64748b; font-size: 12px;")
        self.cat_preview_label = preview
        self.level_sep.textChanged.connect(self._update_cat_preview)
        layout.addWidget(preview)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("一级分类（仅设置页可增删）"))
        self.primary_list = QListWidget()
        self.primary_list.currentRowChanged.connect(self._on_primary_row)
        left.addWidget(self.primary_list)
        pbtns = QHBoxLayout()
        b_add_p = QPushButton("添加一级")
        b_add_p.clicked.connect(self._add_primary)
        b_del_p = QPushButton("删除一级")
        b_del_p.clicked.connect(self._del_primary)
        pbtns.addWidget(b_add_p)
        pbtns.addWidget(b_del_p)
        left.addLayout(pbtns)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("一级名称"))
        self.primary_name = QLineEdit()
        right.addWidget(self.primary_name)

        right.addWidget(QLabel("二级分类"))
        self.secondary_list = QListWidget()
        right.addWidget(self.secondary_list)
        sbtns = QHBoxLayout()
        b_add_s = QPushButton("添加二级")
        b_add_s.clicked.connect(self._add_secondary_setting)
        b_del_s = QPushButton("删除二级")
        b_del_s.clicked.connect(self._del_secondary_setting)
        sbtns.addWidget(b_add_s)
        sbtns.addWidget(b_del_s)
        right.addLayout(sbtns)
        body.addLayout(right, 1)

        layout.addLayout(body, 1)
        self._cat_working: CategorySettings = default_category_settings()
        return page

    def _create_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("🎨 外观主题")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        group = QGroupBox("主题模式")
        form = QFormLayout(group)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("白天（浅色）", "light")
        self.theme_combo.addItem("黑夜（深色）", "dark")
        form.addRow("应用主题:", self.theme_combo)
        layout.addWidget(group)

        hint = QLabel("保存设置后立即生效。跟随系统时使用操作系统浅色/深色偏好。")
        hint.setStyleSheet("color: #888; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        return page

    def _update_cat_preview(self, *_args):
        if not hasattr(self, "cat_preview_label"):
            return
        pair = self.wrap_preset.currentData() if hasattr(self, "wrap_preset") else None
        if pair:
            wl, wr = pair[0], pair[1]
        else:
            wl, wr = "[", "]"
        sep = self.level_sep.text() if hasattr(self, "level_sep") else "-"
        self.cat_preview_label.setText(
            f"标题预览: {wl}工作{sep}需求{wr} 示例任务"
        )

    def _refresh_primary_list(self, select_id: str | None = None):
        self.primary_list.clear()
        wl = self._cat_working.wrap_left
        wr = self._cat_working.wrap_right
        for p in self._cat_working.primary_list:
            item = QListWidgetItem(f"{wl}{p.name}{wr}")
            item.setData(Qt.UserRole, p.id)
            self.primary_list.addItem(item)
        if select_id:
            for i in range(self.primary_list.count()):
                if self.primary_list.item(i).data(Qt.UserRole) == select_id:
                    self.primary_list.setCurrentRow(i)
                    return
        if self.primary_list.count():
            self.primary_list.setCurrentRow(0)

    def _selected_primary(self) -> PrimaryCategory | None:
        item = self.primary_list.currentItem()
        if not item:
            return None
        return self._cat_working.find_primary(item.data(Qt.UserRole))

    def _flush_primary_fields(self):
        p = self._selected_primary()
        if not p:
            return
        name = self.primary_name.text().strip()
        if name:
            p.name = name
        # 全局括号写回 settings
        pair = self.wrap_preset.currentData()
        if pair:
            self._cat_working.wrap_left = pair[0]
            self._cat_working.wrap_right = pair[1]
        self._cat_working.level_separator = self.level_sep.text()

    def _on_primary_row(self, row: int):
        if row < 0:
            return
        self._flush_primary_fields()
        item = self.primary_list.item(row)
        p = self._cat_working.find_primary(item.data(Qt.UserRole)) if item else None
        if not p:
            return
        self.primary_name.setText(p.name)
        self.secondary_list.clear()
        for s in p.secondaries:
            it = QListWidgetItem(s.name)
            it.setData(Qt.UserRole, s.id)
            self.secondary_list.addItem(it)

    def _on_wrap_preset(self, _idx: int = 0):
        self._update_cat_preview()
        # 刷新一级列表预览括号
        cur = self._selected_primary()
        sid = cur.id if cur else None
        pair = self.wrap_preset.currentData()
        if pair:
            self._cat_working.wrap_left = pair[0]
            self._cat_working.wrap_right = pair[1]
        self._refresh_primary_list(sid)

    def _add_primary(self):
        self._flush_primary_fields()
        name, ok = QInputDialog.getText(self, "添加一级分类", "名称:")
        if not ok or not name.strip():
            return
        p = PrimaryCategory(id=str(uuid.uuid4()), name=name.strip())
        self._cat_working.primary_list.append(p)
        self._refresh_primary_list(p.id)

    def _del_primary(self):
        p = self._selected_primary()
        if not p:
            return
        if len(self._cat_working.primary_list) <= 1:
            QMessageBox.warning(self, "无法删除", "至少保留一个一级分类。")
            return
        self._cat_working.primary_list = [
            x for x in self._cat_working.primary_list if x.id != p.id
        ]
        self._refresh_primary_list()

    def _add_secondary_setting(self):
        p = self._selected_primary()
        if not p:
            return
        name, ok = QInputDialog.getText(self, "添加二级分类", "名称:")
        if not ok or not name.strip():
            return
        sec = p.add_secondary(name.strip())
        it = QListWidgetItem(sec.name)
        it.setData(Qt.UserRole, sec.id)
        self.secondary_list.addItem(it)

    def _del_secondary_setting(self):
        p = self._selected_primary()
        item = self.secondary_list.currentItem()
        if not p or not item:
            return
        sid = item.data(Qt.UserRole)
        p.secondaries = [s for s in p.secondaries if s.id != sid]
        self.secondary_list.takeItem(self.secondary_list.currentRow())

    # ==========================================
    # 任务轮播页
    # ==========================================

    def _create_polling_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("📋 任务轮播")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        # --- 轮播模式 ---
        mode_group = QGroupBox("轮播模式")
        mode_form = QFormLayout(mode_group)
        mode_form.setSpacing(8)

        self.rotation_mode = QComboBox()
        self.rotation_mode.addItem("🎲 随机（优先级加权）", "random")
        self.rotation_mode.addItem("🔽 优先级从高到低", "priority_high_first")
        self.rotation_mode.addItem("🔼 优先级从低到高", "priority_low_first")
        mode_form.addRow("排序方式:", self.rotation_mode)

        layout.addWidget(mode_group)

        # --- 停留时间 ---
        dwell_group = QGroupBox("停留时间（秒）")
        dwell_form = QFormLayout(dwell_group)
        dwell_form.setSpacing(10)

        self.high_dwell = QSpinBox()
        self.high_dwell.setRange(1, 60)
        self.high_dwell.setSuffix(" 秒")
        self.high_dwell.setPrefix("🔴 高优  ")
        self.high_dwell.valueChanged.connect(self._validate_polling)
        dwell_form.addRow(self.high_dwell)

        self.medium_dwell = QSpinBox()
        self.medium_dwell.setRange(1, 60)
        self.medium_dwell.setSuffix(" 秒")
        self.medium_dwell.setPrefix("🟡 中优  ")
        self.medium_dwell.valueChanged.connect(self._validate_polling)
        dwell_form.addRow(self.medium_dwell)

        self.low_dwell = QSpinBox()
        self.low_dwell.setRange(1, 60)
        self.low_dwell.setSuffix(" 秒")
        self.low_dwell.setPrefix("🟢 低优  ")
        self.low_dwell.valueChanged.connect(self._validate_polling)
        dwell_form.addRow(self.low_dwell)

        layout.addWidget(dwell_group)

        self.polling_error = QLabel("")
        self.polling_error.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")
        self.polling_error.setWordWrap(True)
        layout.addWidget(self.polling_error)

        # --- 逾期任务 ---
        overdue_group = QGroupBox("逾期任务")
        overdue_layout = QVBoxLayout(overdue_group)
        overdue_layout.setSpacing(8)

        self.cb_overdue_rotation = QCheckBox("轮播已逾期任务（启动时优先显示）")
        self.cb_overdue_rotation.toggled.connect(self._toggle_overdue_group)
        overdue_layout.addWidget(self.cb_overdue_rotation)

        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("逾期标题前缀:"))
        self.overdue_prefix = QLineEdit()
        self.overdue_prefix.setPlaceholderText("【已逾期】")
        self.overdue_prefix.setMaximumWidth(120)
        prefix_layout.addWidget(self.overdue_prefix)
        prefix_layout.addStretch()
        self.overdue_prefix_widget = QWidget()
        self.overdue_prefix_widget.setLayout(prefix_layout)
        overdue_layout.addWidget(self.overdue_prefix_widget)

        layout.addWidget(overdue_group)

        layout.addStretch()
        return page

    def _toggle_overdue_group(self, checked: bool):
        self.overdue_prefix_widget.setEnabled(checked)

    def _validate_polling(self):
        h = self.high_dwell.value()
        m = self.medium_dwell.value()
        l = self.low_dwell.value()
        if h < m:
            self.polling_error.setText(f"⚠️ 高优停留时间（{h}秒）不得少于中优（{m}秒）")
        elif m < l:
            self.polling_error.setText(f"⚠️ 中优停留时间（{m}秒）不得少于低优（{l}秒）")
        else:
            self.polling_error.setText("")

    # ==========================================
    # 番茄钟页
    # ==========================================

    def _create_pomodoro_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("🍅 番茄钟")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        group = QGroupBox("计时设置")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.pomo_duration = QSpinBox()
        self.pomo_duration.setRange(5, 120)
        self.pomo_duration.setSuffix(" 分钟")
        self.pomo_duration.setValue(25)
        form.addRow("专注时长:", self.pomo_duration)

        self.pomo_extend = QSpinBox()
        self.pomo_extend.setRange(1, 60)
        self.pomo_extend.setSuffix(" 分钟")
        self.pomo_extend.setValue(10)
        form.addRow("每次延长:", self.pomo_extend)

        layout.addWidget(group)
        layout.addStretch()
        return page

    # ==========================================
    # 系统页 → 桌面快捷方式 + 开机自启
    # ==========================================

    def _create_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        header = QLabel("💻 系统设置")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        # 桌面快捷方式（仅 Windows 显示）
        self.shortcut_group = QGroupBox("桌面快捷方式")
        self.shortcut_group.setVisible(sys.platform == "win32")
        shortcut_layout = QVBoxLayout(self.shortcut_group)
        self.cb_shortcut = QCheckBox("在桌面创建 ZenTray 快捷方式")
        shortcut_layout.addWidget(self.cb_shortcut)
        self.shortcut_status = QLabel("")
        self.shortcut_status.setStyleSheet("color: #888; font-size: 11px;")
        shortcut_layout.addWidget(self.shortcut_status)
        layout.addWidget(self.shortcut_group)

        # 开机自启
        autostart_group = QGroupBox("开机启动")
        autostart_layout = QVBoxLayout(autostart_group)
        self.cb_autostart = QCheckBox("系统启动时自动运行 ZenTray")
        autostart_layout.addWidget(self.cb_autostart)
        self.autostart_status = QLabel("")
        self.autostart_status.setStyleSheet("color: #888; font-size: 11px;")
        autostart_layout.addWidget(self.autostart_status)
        layout.addWidget(autostart_group)

        layout.addStretch()

        hint = QLabel("这些设置会在保存时立即生效。")
        hint.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(hint)

        return page

    # ==========================================
    # 加载 / 保存
    # ==========================================

    def _load_values(self):
        """从 SettingsManager 和系统加载当前值"""
        s = self._settings

        # AI 教练
        self.ai_enabled.setChecked(s.ai.enabled)
        self.ai_key.setText(s.ai.api_key)
        self.ai_base.setText(s.ai.base_url)
        self.ai_model.setText(s.ai.model)
        self.ai_group.setEnabled(s.ai.enabled)

        self._styles_working = merge_styles([x.to_dict() for x in s.ai.styles])
        self._reload_style_combo(s.ai.active_style_id)

        # 分类
        self._cat_working = CategorySettings.from_dict(s.categories.to_dict())
        self.cb_sec_enabled.setChecked(self._cat_working.enabled_secondary)
        self.level_sep.setText(self._cat_working.level_separator)
        # 匹配括号预设
        matched = False
        for i in range(self.wrap_preset.count()):
            pair = self.wrap_preset.itemData(i)
            if pair and pair[0] == self._cat_working.wrap_left and pair[1] == self._cat_working.wrap_right:
                self.wrap_preset.setCurrentIndex(i)
                matched = True
                break
        if not matched:
            self.wrap_preset.setCurrentIndex(0)
        self._refresh_primary_list()
        self._update_cat_preview()

        # 外观
        tidx = self.theme_combo.findData(s.appearance.theme)
        if tidx < 0:
            tidx = self.theme_combo.findData("system")
        if tidx >= 0:
            self.theme_combo.setCurrentIndex(tidx)

        # 夜间复盘时间
        self.nightly_hour.setValue(s.nightly.trigger_hour)
        self.nightly_minute.setValue(s.nightly.trigger_minute)
        self.cb_skip_weekends.setChecked(bool(getattr(s.nightly, "skip_weekends", False)))
        self.cb_skip_holidays.setChecked(bool(getattr(s.nightly, "skip_holidays", False)))

        # 通知（与 AI 同页）
        self.notif_enabled.setChecked(s.notification.enabled)
        self.wx_token.setText(s.notification.wxpusher_app_token)
        self.wx_uid.setText(s.notification.wxpusher_uid)
        self.notif_group.setEnabled(s.notification.enabled)

        # 轮播
        self.high_dwell.setValue(s.polling.high_priority_seconds)
        self.medium_dwell.setValue(s.polling.medium_priority_seconds)
        self.low_dwell.setValue(s.polling.low_priority_seconds)
        self._validate_polling()

        # 轮播模式
        mode_idx = self.rotation_mode.findData(s.polling.rotation_mode)
        if mode_idx >= 0:
            self.rotation_mode.setCurrentIndex(mode_idx)

        # 逾期
        self.cb_overdue_rotation.setChecked(s.polling.enable_overdue_rotation)
        self.overdue_prefix.setText(s.polling.overdue_prefix)
        self._toggle_overdue_group(s.polling.enable_overdue_rotation)

        # 番茄钟
        self.pomo_duration.setValue(s.pomodoro.duration_minutes)
        self.pomo_extend.setValue(s.pomodoro.extend_minutes)

        # 系统设置
        shortcut_exists = is_shortcut_created(APP_NAME)
        self.cb_shortcut.setChecked(shortcut_exists)
        self.shortcut_status.setText(
            "✅ 桌面快捷方式已创建" if shortcut_exists
            else "桌面快捷方式未创建"
        )

        autostart_enabled = is_autostart_enabled(APP_NAME)
        self.cb_autostart.setChecked(autostart_enabled)
        self.autostart_status.setText(
            "✅ 已设置开机自启" if autostart_enabled
            else "开机自启未设置"
        )

    def _save_and_accept(self):
        """校验并保存"""
        # 轮播校验
        if self.polling_error.text():
            QMessageBox.warning(
                self, "校验失败",
                "请修正任务轮播设置：\n高优停留时间 ≥ 中优 ≥ 低优。"
            )
            # 切换到轮播页（index=2）
            for i in range(self.nav_list.count()):
                item = self.nav_list.item(i)
                if item and item.data(Qt.UserRole) == 2:
                    self.nav_list.setCurrentRow(i)
                    break
            return

        # 写入功能设置
        s = self._settings
        s.polling.high_priority_seconds = self.high_dwell.value()
        s.polling.medium_priority_seconds = self.medium_dwell.value()
        s.polling.low_priority_seconds = self.low_dwell.value()
        s.polling.rotation_mode = self.rotation_mode.currentData()
        s.polling.enable_overdue_rotation = self.cb_overdue_rotation.isChecked()
        s.polling.overdue_prefix = self.overdue_prefix.text().strip() or "【已逾期】"
        s.pomodoro.duration_minutes = self.pomo_duration.value()
        s.pomodoro.extend_minutes = self.pomo_extend.value()
        s.nightly.trigger_hour = self.nightly_hour.value()
        s.nightly.trigger_minute = self.nightly_minute.value()
        s.nightly.skip_weekends = self.cb_skip_weekends.isChecked()
        s.nightly.skip_holidays = self.cb_skip_holidays.isChecked()
        s.notification.enabled = self.notif_enabled.isChecked()
        s.notification.wxpusher_app_token = self.wx_token.text().strip()
        s.notification.wxpusher_uid = self.wx_uid.text().strip()
        s.ai.enabled = self.ai_enabled.isChecked()
        s.ai.api_key = self.ai_key.text().strip()
        s.ai.base_url = self.ai_base.text().strip()
        s.ai.model = self.ai_model.text().strip()

        self._flush_style_prompt_to_working()
        s.ai.styles = list(self._styles_working)
        s.ai.active_style_id = self.ai_style_combo.currentData() or STYLE_TOXIC

        self._flush_primary_fields()
        self._cat_working.enabled_secondary = self.cb_sec_enabled.isChecked()
        self._cat_working.level_separator = self.level_sep.text()
        pair = self.wrap_preset.currentData()
        if pair:
            self._cat_working.wrap_left = pair[0]
            self._cat_working.wrap_right = pair[1]
        s.categories = self._cat_working

        s.appearance.theme = self.theme_combo.currentData() or "system"

        # 持久化功能设置
        self._manager.save()

        # 立即应用主题
        try:
            from zentray.ui.theme import apply_app_theme

            apply_app_theme(s.appearance.theme)
        except Exception:
            pass

        # 系统设置：按需操作
        shortcut_wanted = self.cb_shortcut.isChecked()
        if shortcut_wanted != is_shortcut_created(APP_NAME):
            toggle_shortcut(shortcut_wanted, APP_NAME)

        autostart_wanted = self.cb_autostart.isChecked()
        if autostart_wanted != is_autostart_enabled(APP_NAME):
            toggle_autostart(autostart_wanted, APP_NAME)

        self.accept()
