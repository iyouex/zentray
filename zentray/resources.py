# zentray/resources.py
"""
资源文件管理 —— 兼容开发模式和 PyInstaller 打包模式。
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 与 scripts/generate_pie_icons.py 保持一致；变更时强制刷新用户目录饼图
# v4: 任务饼图无绿叶；番茄独立绘制（红果+绿萼，随进度填充）
PIE_ICON_VERSION = "4"


def get_resource_path(relative_path: str) -> Path:
    """获取资源文件绝对路径，兼容开发 / PyInstaller 两种模式。"""
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_path = Path(__file__).parent.parent
    return base_path / relative_path


def get_user_data_dir() -> Path:
    """
    用户数据目录 —— 与 config.DATA_DIR 保持一致。

    Linux: $XDG_DATA_HOME/ZenTray 或 ~/.local/share/ZenTray
    """
    # 延迟导入避免循环：config 可能 import resources
    try:
        from zentray.config import DATA_DIR

        return Path(DATA_DIR)
    except Exception:
        xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        return Path(xdg) / "ZenTray"


def ensure_data_dirs() -> Path:
    """确保用户数据目录与 archive/icons 存在，返回 DATA_DIR。"""
    data_dir = get_user_data_dir()
    (data_dir / "archive").mkdir(parents=True, exist_ok=True)
    (data_dir / "icons").mkdir(parents=True, exist_ok=True)
    (data_dir / "reviews").mkdir(parents=True, exist_ok=True)
    return data_dir


def _snap_progress_10(progress: int | None = 0) -> int:
    try:
        pct = int(progress if progress is not None else 0)
    except (TypeError, ValueError):
        pct = 0
    pct = max(0, min(100, pct))
    snapped = int(round(pct / 10.0) * 10)
    return max(0, min(100, snapped))


def tray_pie_icon_name(priority: str | None, progress: int | None = 0) -> str:
    """
    顶栏轮播用的优先级饼图图标名。

    - 颜色（紧急程度）：high=红, medium=黄, low=绿, 其它=灰
    - 扇形占比：任务 progress 0–100，对齐到 10% 步进资源
      资源名：pie_{priority}_{0|10|…|100}.png
    """
    p = (priority or "").strip().lower()
    if p not in ("high", "medium", "low"):
        p = "none"
    return f"pie_{p}_{_snap_progress_10(progress)}"


def tray_tomato_icon_name(progress: int | None = 0) -> str:
    """
    番茄钟倒计时饼图：tomato_{0|10|…|100}.png
    progress 为已消耗进度 0–100（0=刚开始半透明，100=满实心）。
    """
    return f"tomato_{_snap_progress_10(progress)}"


def _pie_version_path(icon_dir: Path) -> Path:
    return icon_dir / ".pie_icons_version"


def _needs_pie_refresh(icon_dir: Path) -> bool:
    ver_file = _pie_version_path(icon_dir)
    if not ver_file.exists():
        return True
    try:
        return ver_file.read_text(encoding="utf-8").strip() != PIE_ICON_VERSION
    except OSError:
        return True


def _generate_pie_icons_into(icon_dir: Path) -> bool:
    """用 Pillow 生成任务优先级饼图 + 番茄钟图标；失败返回 False。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow 不可用，无法生成饼图图标")
        return False

    colors = {
        "high": (239, 68, 68),
        "medium": (245, 158, 11),
        "low": (34, 197, 94),
        "none": (148, 163, 184),
    }
    # 番茄：偏圆润的果红 + 深绿萼（与 🍅 语义一致；与 high 饼图分开绘制）
    tomato_body = (228, 56, 48)
    tomato_leaf = (34, 160, 70)
    base_alpha = 72
    outline_alpha = 230
    size = 32

    def _draw_priority_pie(rgb, progress: int) -> "Image.Image":
        """任务紧急程度饼图：纯色环/扇形，无绿点。"""
        r, g, b = rgb
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        margin = 1
        bbox = [margin, margin, size - 1 - margin, size - 1 - margin]
        draw.ellipse(
            bbox,
            fill=(r, g, b, base_alpha),
            outline=(r, g, b, outline_alpha),
            width=2,
        )
        if progress >= 100:
            draw.ellipse(
                bbox,
                fill=(r, g, b, 255),
                outline=(r, g, b, 255),
                width=2,
            )
        elif progress > 0:
            start = -90.0
            end = -90.0 + progress * 3.6
            draw.pieslice(bbox, start=start, end=end, fill=(r, g, b, 255))
            draw.ellipse(bbox, outline=(r, g, b, outline_alpha), width=2)
        return im

    def _draw_tomato(progress: int) -> "Image.Image":
        """
        番茄钟图标：圆形番茄果 + 顶部绿萼/小茎，
        果体随 progress 做饼状实心填充（与菜单 🍅 语义一致）。
        """
        r, g, b = tomato_body
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        # 果体略下移，给绿萼留空
        margin_x, margin_top, margin_bot = 2, 5, 1
        bbox = [margin_x, margin_top, size - 1 - margin_x, size - 1 - margin_bot]
        draw.ellipse(
            bbox,
            fill=(r, g, b, base_alpha),
            outline=(r, g, b, outline_alpha),
            width=2,
        )
        if progress >= 100:
            draw.ellipse(
                bbox,
                fill=(r, g, b, 255),
                outline=(r, g, b, 255),
                width=2,
            )
        elif progress > 0:
            start = -90.0
            end = -90.0 + progress * 3.6
            draw.pieslice(bbox, start=start, end=end, fill=(r, g, b, 255))
            draw.ellipse(bbox, outline=(r, g, b, outline_alpha), width=2)

        # 绿萼：中心小茎 + 两侧小叶（仅番茄）
        lr, lg, lb = tomato_leaf
        cx = size // 2
        # 茎
        draw.rectangle([cx - 1, 2, cx + 1, 7], fill=(lr, lg, lb, 255))
        # 左叶 / 右叶
        draw.ellipse([cx - 7, 2, cx - 1, 8], fill=(lr, lg, lb, 240))
        draw.ellipse([cx + 1, 2, cx + 7, 8], fill=(lr, lg, lb, 240))
        # 中上小叶
        draw.ellipse([cx - 3, 1, cx + 3, 6], fill=(lr, lg, lb, 255))
        return im

    icon_dir.mkdir(parents=True, exist_ok=True)
    for priority, rgb in colors.items():
        for progress in range(0, 101, 10):
            im = _draw_priority_pie(rgb, progress)
            im.save(icon_dir / f"pie_{priority}_{progress}.png", "PNG")

    for progress in range(0, 101, 10):
        im = _draw_tomato(progress)
        im.save(icon_dir / f"tomato_{progress}.png", "PNG")

    try:
        _pie_version_path(icon_dir).write_text(PIE_ICON_VERSION + "\n", encoding="utf-8")
    except OSError:
        pass
    logger.info("已生成饼图/番茄图标 v%s → %s", PIE_ICON_VERSION, icon_dir)
    return True


def ensure_app_icons() -> Path:
    """
    将打包/开发资源中的图标同步到 DATA_DIR/icons，并保证饼图为 v2 视觉。

    - pie_*.png：版本标记变更时强制重新生成/覆盖
    - app_icon.png：资源更新后强制同步
    """
    data_dir = ensure_data_dirs()
    icon_dir = data_dir / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)

    src_dir = get_resource_path("resources/icons")

    # 先同步 app_icon
    if src_dir.is_dir():
        for fname in os.listdir(src_dir):
            if fname != "app_icon.png":
                continue
            src = src_dir / fname
            if not src.is_file():
                continue
            dst = icon_dir / fname
            try:
                if (
                    not dst.exists()
                    or src.stat().st_mtime > dst.stat().st_mtime
                    or src.stat().st_size != dst.stat().st_size
                ):
                    shutil.copy2(src, dst)
            except OSError:
                pass

    # 饼图：优先本地生成 v2；失败则从打包资源拷贝
    if _needs_pie_refresh(icon_dir):
        ok = _generate_pie_icons_into(icon_dir)
        if not ok and src_dir.is_dir():
            for fname in os.listdir(src_dir):
                if not (fname.startswith("pie_") and fname.endswith(".png")):
                    continue
                src = src_dir / fname
                dst = icon_dir / fname
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass
            try:
                _pie_version_path(icon_dir).write_text(
                    PIE_ICON_VERSION + "\n", encoding="utf-8"
                )
            except OSError:
                pass
    else:
        # 补齐缺失的 pie / tomato
        missing = False
        for priority in ("high", "medium", "low", "none"):
            for pct in range(0, 101, 10):
                if not (icon_dir / f"pie_{priority}_{pct}.png").exists():
                    missing = True
                    break
            if missing:
                break
        if not missing:
            for pct in range(0, 101, 10):
                if not (icon_dir / f"tomato_{pct}.png").exists():
                    missing = True
                    break
        if missing:
            if not _generate_pie_icons_into(icon_dir) and src_dir.is_dir():
                for fname in os.listdir(src_dir):
                    if not fname.endswith(".png"):
                        continue
                    if not (fname.startswith("pie_") or fname.startswith("tomato_")):
                        continue
                    src = src_dir / fname
                    dst = icon_dir / fname
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass

    # 迁移旧路径 ~/.local/share/zentray/icons（Linux 历史小写目录）
    if sys.platform.startswith("linux"):
        xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        legacy = Path(xdg) / "zentray" / "icons"
        if legacy.is_dir() and legacy.resolve() != icon_dir.resolve():
            for fname in os.listdir(legacy):
                if not fname.endswith(".png") or fname == "app_icon.png":
                    continue
                if fname.startswith("pie_"):
                    continue  # 不用旧饼图覆盖 v2
                src = legacy / fname
                dst = icon_dir / fname
                if not dst.exists():
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass

    return icon_dir
