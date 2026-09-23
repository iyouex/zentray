# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件。

构建命令:
    pyinstaller zentray.spec

输出:
    dist/ZenTray  (Linux)
    dist/ZenTray.app  (macOS)
    dist/ZenTray.exe  (Windows)

体积说明:
  自包含打包必带 Chromium 内核 (QtWebEngine ~100MB+)，这是内嵌 Vue 对话框的代价。
  本 spec 会剔除图表/3D/多媒体/多余翻译等业务用不到的 Qt 组件以瘦身。
"""

import re
import sys
from pathlib import Path

# ---------- 基础分析 ----------
block_cipher = None

# 业务不需要的 Qt 模块/插件（Widgets + WebEngine 对话框足够）
# 注意：不可剔除 WebEngine / WebChannel / 核心 Quick·Qml（WebEngine 依赖）
_EXCLUDE_NAME_RES = [
    re.compile(p, re.I)
    for p in [
        # 3D / 图表 / 可视化
        r"Quick3D",
        r"Qt6?3D",
        r"Charts",
        r"Graphs",
        r"DataVisualization",
        # 多媒体 / 位置 / 外设
        r"Multimedia",
        r"Location",
        r"Sensors",
        r"SerialPort",
        r"SerialBus",
        r"Bluetooth",
        r"Nfc",
        r"TextToSpeech",
        r"VirtualKeyboard",
        # 设计器 / 状态机 / 远程
        r"Designer",
        r"Help",
        r"UiTools",
        r"RemoteObjects",
        r"Scxml",
        r"StateMachine",
        r"QtWebView",  # 非 WebEngine
        # PDF 模块（业务未用；WebEngine 本身可渲染简单 PDF 若需要）
        r"Qt6?Pdf",
        r"PdfWidgets",
        # 多余 QML 控件样式（Fluent / Material / Imagine 等）
        r"FluentWinUI3",
        r"QuickControls2Imagine",
        r"QuickControls2Material",
        r"QuickControls2Universal",
        r"QuickControls2Fusion",
        r"QuickControls2Windows",
        r"QuickControls2macOS",
        r"QuickControls2IOS",
        r"QuickControls2Android",
        # 开发者工具资源（生产不需要）
        r"devtools",
        r"qtwebengine_devtools",
        # 示例 / 文档
        r"/examples/",
        r"/doc/",
    ]
]

# 仅保留中英文翻译（若存在）
_KEEP_TRANSLATION = re.compile(
    r"qt_?.*_(zh_CN|zh_TW|en|en_US)\.", re.I
)
_IS_TRANSLATION = re.compile(
    r"translations[/\\].*\.(qm|pak)$|[/\\]qt_..(_..)?\.qm$", re.I
)


def _should_exclude(name: str) -> bool:
    n = name.replace("\\", "/")
    if _IS_TRANSLATION.search(n):
        return _KEEP_TRANSLATION.search(n) is None
    for rx in _EXCLUDE_NAME_RES:
        if rx.search(n):
            return True
    return False


def _filter_toc(toc):
    """过滤 (dest_name, src_path, typecode) 三元组列表。"""
    kept = []
    dropped = 0
    for entry in toc:
        # entry: (name, path, typecode) or similar
        name = entry[0] if entry else ""
        if _should_exclude(str(name)):
            dropped += 1
            continue
        kept.append(entry)
    if dropped:
        print(f"[zentray.spec] filtered out {dropped} binaries/datas for size")
    return kept


a = Analysis(
    ['zentray/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 样式文件
        ('zentray/ui/styles/*.qss', 'zentray/ui/styles'),
        # 图标资源
        ('resources/icons/*.png', 'resources/icons'),
        # Linux 托盘桥接脚本（subprocess 调用，PyInstaller 无法自动发现）
        ('zentray/ui/linux_tray_bridge.py', 'zentray/ui'),
        # Vue + Arco 构建产物（需先 npm run build）
        ('web/dist', 'web/dist'),
    ],
    hiddenimports=[
        # 核心模块
        'zentray.core.models',
        'zentray.core.scheduler',
        'zentray.core.repository',
        'zentray.repositories.file_repository',
        'zentray.repositories.file_periodic_repository',
        'zentray.services.task_service',
        'zentray.services.pomodoro_service',
        'zentray.services.notification',
        'zentray.services.ai_review',
        'zentray.ui.controller',
        'zentray.ui.renderer',
        'zentray.ui.menu_builder',
        'zentray.ui.commands',
        'zentray.ui.vue_commands',
        'zentray.ui.web_host',
        'zentray.ui.tray',
        'zentray.ui.dialogs',
        'zentray.ui.overlay',
        'zentray.api.server',
        'zentray.api.handlers',
        'zentray.workers.watcher',
        'zentray.workers.nightly_job',
        # DI 容器
        'zentray.dependencies',
        # pynput 平台特定后端
        'pynput.keyboard._xorg',
        'pynput.keyboard._win32',
        'pynput.keyboard._darwin',
        # WebEngine
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除不需要的重量级库以减小包体积
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtGraphs',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtTextToSpeech',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtQuick3D',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtUiTools',
        'PySide6.QtWebView',
        'PySide6.scripts',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
)

# ---------- 过滤不必要的二进制 / 数据 ----------
a.binaries = _filter_toc(a.binaries)
a.datas = _filter_toc(a.datas)

pyz = PYZ(a.pure, a.zipped_data)

# ---------- 可执行文件 ----------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ZenTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,                 # strip 符号表，略减体积
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # 无控制台窗口（GUI 应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 图标（根据平台选择）
    icon='resources/icons/app_icon.ico' if sys.platform == 'win32' else 'resources/icons/app_icon.png',
)
