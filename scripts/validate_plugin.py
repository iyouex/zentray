#!/usr/bin/env python3
"""校验插件目录是否符合 ZenTray 插件规范。"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从仓库根直接运行
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zentray.plugins.manifest import validate_plugin_dir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print("用法: python scripts/validate_plugin.py <plugin_dir> [<plugin_dir> ...]")
        return 0 if args else 2
    failed = 0
    for raw in args:
        path = Path(raw)
        result = validate_plugin_dir(path)
        if result.ok:
            m = result.manifest
            print(f"OK  {path}  id={m.id} type={m.type.value} entry={m.entry}")
        else:
            failed += 1
            print(f"FAIL {path}")
            for e in result.errors:
                print(f"  - {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
