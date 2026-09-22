# zentray/ui/setup_wizard.py
"""
首次启动配置向导。

引导用户完成可选功能的配置（通知推送、AI 教练），
所有步骤均可跳过，核心功能始终可用。
"""
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QWidget, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class SetupWizard(QDialog):
    """首次启动配置向导"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用 ZenTray — 初始配置")
        from zentray.ui.dialog_utils import apply_dialog_chrome, style_action_button

        apply_dialog_chrome(self, width=640, height=420)
        self._style_btn = style_action_button

        from zentray.config import DATA_DIR, _PROJECT_ROOT

        # 优先写入用户数据目录；开发环境额外尝试项目根 .env
        self.data_dir = DATA_DIR
        self.user_env_path = DATA_DIR / ".env"
        self.project_env_path = _PROJECT_ROOT / ".env"
        self.setup_marker = DATA_DIR / ".setup_done"
        self._config_data = {}

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        # 标题
        title = QLabel("🚀 欢迎使用 ZenTray")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel("核心功能已就绪！以下为可选配置，全部可跳过。")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(subtitle)

        # 步骤堆栈
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.stack.addWidget(self._welcome_page())
        self.stack.addWidget(self._notification_page())
        self.stack.addWidget(self._ai_page())
        self.stack.addWidget(self._finish_page())

        # 底部按钮（横排，保证文字完整）
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_skip_all = self._style_btn(QPushButton("⏭️ 跳过全部"), min_w=110)
        self.btn_skip_all.clicked.connect(self._skip_all)
        btn_layout.addWidget(self.btn_skip_all)

        btn_layout.addStretch()

        self.btn_back = self._style_btn(QPushButton("← 上一步"), min_w=100)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_back.setVisible(False)
        btn_layout.addWidget(self.btn_back)

        self.btn_next = self._style_btn(QPushButton("下一步 →"), min_w=110)
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._go_next)
        btn_layout.addWidget(self.btn_next)

        layout.addLayout(btn_layout)

    # ==========================================
    # 欢迎页
    # ==========================================

    def _welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        info = QLabel(
            "ZenTray 是一款跨平台个人效率工具，帮助你管理待办任务、\n"
            "保持专注节奏。\n\n"
            "✅ 核心功能（始终可用）：\n"
            "   • 任务创建、分类、优先级管理\n"
            "   • 番茄钟专注计时\n"
            "   • 系统托盘轮播看板\n"
            "   • 全局快捷键闪电添加\n\n"
            "⚡ 可选功能（需简单配置）：\n"
            "   • 移动端消息推送（WxPusher）\n"
            "   • AI 每日毒舌复盘教练\n\n"
            "点击「下一步」开始快速配置，或直接「跳过全部」开始使用。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 13px; line-height: 1.6;")
        layout.addWidget(info)

        return page

    # ==========================================
    # 通知配置页
    # ==========================================

    def _notification_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        header = QLabel("📱 移动端消息推送（可选）")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        desc = QLabel(
            "配置 WxPusher 后，可在手机上接收任务提醒和夜间复盘报告。\n"
            "获取方式：访问 wxpusher.zjiecode.com 注册并创建应用。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("App Token:"))
        self.wx_token = QLineEdit()
        self.wx_token.setPlaceholderText("AT_xxxxxxxxxxxxxxxxxxxx")
        layout.addWidget(self.wx_token)

        layout.addWidget(QLabel("UID:"))
        self.wx_uid = QLineEdit()
        self.wx_uid.setPlaceholderText("UID_xxxxxxxxxxxxxxxxxxxx")
        layout.addWidget(self.wx_uid)

        skip_hint = QLabel("留空即可跳过，后续可在 .env 文件中手动配置。")
        skip_hint.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(skip_hint)

        layout.addStretch()
        return page

    # ==========================================
    # AI 配置页
    # ==========================================

    def _ai_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        header = QLabel("🤖 AI 每日复盘教练（可选）")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        desc = QLabel(
            "配置 AI API 后，ZenTray 将在每晚 23:30 自动生成你的当日\n"
            "任务执行复盘报告，毒舌锐评你的摸鱼行为，并规划明日重点。\n"
            "支持 OpenAI 兼容 API（包括 DeepSeek 等国产模型）。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("API Key:"))
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setPlaceholderText("sk-xxxxxxxxxxxxxxxxxxxxxxxx")
        layout.addWidget(self.ai_key)

        layout.addWidget(QLabel("API Base URL (可选):"))
        self.ai_base = QLineEdit()
        self.ai_base.setPlaceholderText("https://api.openai.com/v1")
        layout.addWidget(self.ai_base)

        layout.addWidget(QLabel("模型名称 (可选):"))
        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText("gpt-4o")
        layout.addWidget(self.ai_model)

        skip_hint = QLabel("留空即可跳过，后续可在 .env 文件中手动配置。")
        skip_hint.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(skip_hint)

        layout.addStretch()
        return page

    # ==========================================
    # 完成页
    # ==========================================

    def _finish_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("🎉")
        icon.setAlignment(Qt.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(48)
        icon.setFont(icon_font)
        layout.addWidget(icon)

        msg = QLabel("一切就绪！")
        msg.setAlignment(Qt.AlignCenter)
        msg_font = QFont()
        msg_font.setPointSize(16)
        msg_font.setBold(True)
        msg.setFont(msg_font)
        layout.addWidget(msg)

        self.finish_detail = QLabel()
        self.finish_detail.setAlignment(Qt.AlignCenter)
        self.finish_detail.setStyleSheet("color: #666; font-size: 13px;")
        layout.addWidget(self.finish_detail)

        layout.addStretch()
        return page

    # ==========================================
    # 导航逻辑
    # ==========================================

    def _go_next(self):
        current = self.stack.currentIndex()
        if current < self.stack.count() - 1:
            self.stack.setCurrentIndex(current + 1)
            self._update_nav()
        else:
            self._save_and_accept()

    def _go_back(self):
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            self._update_nav()

    def _update_nav(self):
        current = self.stack.currentIndex()
        is_last = current == self.stack.count() - 1
        is_first = current == 0

        self.btn_back.setVisible(not is_first)
        self.btn_next.setText("🚀 开始使用" if is_last else "下一步 →")

        # 更新完成页信息
        if is_last:
            parts = []
            parts.append("✅ 核心功能：已就绪")
            parts.append(
                "✅ 消息推送：已配置" if self.wx_token.text().strip()
                else "⏭️ 消息推送：已跳过"
            )
            parts.append(
                "✅ AI 教练：已配置" if self.ai_key.text().strip()
                else "⏭️ AI 教练：已跳过"
            )
            self.finish_detail.setText("\n".join(parts))

    def _mark_setup_done(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.setup_marker.write_text("ok\n", encoding="utf-8")
        except OSError:
            pass

    def _skip_all(self) -> None:
        """跳过全部可选配置，写入完成标记后进入主程序。"""
        self._mark_setup_done()
        self.accept()

    def reject(self) -> None:
        """关闭窗口也视为完成向导，避免反复弹出。"""
        self._mark_setup_done()
        super().reject()

    def closeEvent(self, event) -> None:
        self._mark_setup_done()
        super().closeEvent(event)

    def _save_and_accept(self):
        """保存配置到 SettingsManager + 用户数据目录 .env，并打完成标记。"""
        from zentray.services.settings_manager import SettingsManager

        wx_token = self.wx_token.text().strip()
        wx_uid = self.wx_uid.text().strip()
        ai_key = self.ai_key.text().strip()
        ai_base = self.ai_base.text().strip()
        ai_model = self.ai_model.text().strip()

        sm = SettingsManager.reload()
        if wx_token:
            sm.notification.wxpusher_app_token = wx_token
        if wx_uid:
            sm.notification.wxpusher_uid = wx_uid
        if ai_key:
            sm.ai.api_key = ai_key
        if ai_base:
            sm.ai.base_url = ai_base
        if ai_model:
            sm.ai.model = ai_model
        sm.save()

        lines = []
        if wx_token:
            lines.append(f"WXPUSHER_APP_TOKEN={wx_token}")
        if wx_uid:
            lines.append(f"WXPUSHER_UID={wx_uid}")
        if ai_key:
            lines.append(f"AI_API_KEY={ai_key}")
        if ai_base:
            lines.append(f"AI_API_BASE_URL={ai_base}")
        if ai_model:
            lines.append(f"AI_MODEL_NAME={ai_model}")
        content = (
            "\n".join(lines) + "\n"
            if lines
            else "# ZenTray 配置文件\n# 可选功能凭据请参见 README\n"
        )
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.user_env_path.write_text(content, encoding="utf-8")
        except OSError:
            pass
        try:
            if not self.project_env_path.exists():
                self.project_env_path.write_text(content, encoding="utf-8")
        except OSError:
            pass

        self._mark_setup_done()
        self.accept()


def should_show_wizard() -> bool:
    """首次运行且尚未完成向导时显示。"""
    from zentray.config import DATA_DIR

    marker = DATA_DIR / ".setup_done"
    if marker.exists():
        return False
    # 若用户已通过 settings.json 配置过，也视为完成
    if (DATA_DIR / "settings.json").exists():
        return False
    return True


def show_setup_wizard(parent=None) -> bool:
    """显示配置向导，返回 True 表示用户完成配置"""
    from zentray.ui.dialog_utils import run_modal_loop

    wizard = SetupWizard(parent)
    return run_modal_loop(wizard)

