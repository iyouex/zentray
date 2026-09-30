#!/usr/bin/env python3
"""生成托盘优先级饼图与番茄钟图标到 resources/icons/。

- pie_{high|medium|low|none}_{0..100}: 任务紧急度饼图（无绿叶）
- tomato_{0..100}: 番茄钟饼图（红果 + 绿萼，随进度填充）
- break_{0..100}: 休息段饼图（茶绿纯色圆饼）
"""
from __future__ import annotations

import sys
from pathlib import Path

# 复用运行时同一套生成逻辑，避免双份实现漂移
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from zentray.resources import PIE_ICON_VERSION, _generate_pie_icons_into  # noqa: E402


def main() -> int:
    out = _ROOT / "resources" / "icons"
    if not _generate_pie_icons_into(out):
        print("生成失败（需要 Pillow）", file=sys.stderr)
        return 1
    print(f"已生成饼图/番茄图标 → {out} (version={PIE_ICON_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
