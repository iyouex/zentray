#!/usr/bin/env python3
"""ZenTray 标准化自测编排器（Linux 本机全量；win/mac 走 CI 门禁+本工具的页面逻辑等价部分）。

用法：
  venv/bin/python tools/selftest/run.py                # 3 轮全量
  venv/bin/python tools/selftest/run.py --rounds 1 --only toolbox
  venv/bin/python tools/selftest/run.py --groups toolbox,cdn

设计要点（详见 .agents/skills/zentray-selftest/SKILL.md）：
  - 双服务器完全隔离：主应用 UI（patch DATA_DIR→临时 + 种子数据）与 text-toolbox
    （env ZENTRAY_PLUGIN_DATA_DIR→临时）绝不触碰真实 ~/.local/share/ZenTray
  - CDN 三态矩阵：normal / blocked(立即断) / hang(挂起>超时) —— 页面可用性不得依赖 CDN
  - 每轮数据规模递增（小/中/大），对抗「只在某规模下坏」的回归
  - 判据：DCL 时延 / console 零 pageerror / DOM 断言 / 功能输出 / 大文本性能上限
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CHROME = "/usr/bin/google-chrome"


# ---------------------------------------------------------------- 服务器引导
class AppServer:
    """主应用 API+Vue UI（无头）：临时数据目录 + 种子任务/模板。"""

    def __init__(self, tmp: Path, scale: str):
        self.tmp = tmp
        self.scale = scale
        self.base_url = ""

    def start(self) -> str:
        import zentray.config as cfg

        data = self.tmp / "appdata"
        (data / "archive").mkdir(parents=True, exist_ok=True)
        # 迟绑定路径补丁（D4 同款教训：模块级常量会被 import 拷贝）
        import zentray.repositories.file_repository as fr
        import zentray.repositories.file_periodic_repository as pr
        import zentray.services.settings_manager as sm

        cfg.DATA_DIR = data
        cfg.ACTIVE_TASKS_FILE = data / "active_tasks.json"
        cfg.PERIODIC_TEMPLATES_FILE = data / "periodic_templates.json"
        cfg.ARCHIVE_DIR = data / "archive"
        sm.DATA_DIR = data
        sm.SETTINGS_FILE = data / "settings.json"

        from zentray.core.scheduler import Scheduler
        from zentray.repositories.file_periodic_repository import (
            FilePeriodicTemplateRepository,
        )
        from zentray.repositories.file_repository import FileTaskRepository
        from zentray.services.task_service import TaskService

        svc = TaskService(
            FileTaskRepository(active_file=cfg.ACTIVE_TASKS_FILE, archive_dir=cfg.ARCHIVE_DIR),
            FilePeriodicTemplateRepository(filepath=cfg.PERIODIC_TEMPLATES_FILE),
            Scheduler(),
        )
        n = {"small": 3, "medium": 40, "large": 150}[self.scale]
        for i in range(n):
            svc.create_task(
                {
                    "title": f"自测任务{i}-{random.choice(['日常', '紧急', '跟进'])}",
                    "category": "工作",
                    "priority": random.choice(["high", "medium", "low"]),
                }
            )
        if self.scale != "small":
            svc.create_template(
                {"title": "自测周模板", "category": "工作", "periodicity": "weekly"}
            )

        from zentray.api.handlers import ApiContext, set_api_context

        set_api_context(ApiContext(task_service=svc))
        from zentray.api.server import LocalApiServer

        self.svc = svc
        self.base_url = LocalApiServer().start()
        return self.base_url

    def stop(self):
        pass


class ToolboxServer:
    """text-toolbox 服务（生产同款入口），env 隔离数据目录。"""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.port = 0
        self.proc = None

    def start(self) -> str:
        import socket
        import subprocess

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        # toolbox 的 /api/tasks 读 ZENTRAY_PLUGIN_DATA_DIR 上两级 = tmp/appdata
        # （与 AppServer 同一数据目录 → 万年历「当日任务」有种子数据可联测）
        import os

        pdir = self.tmp / "appdata" / "plugin_data" / "text-toolbox"
        pdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["ZENTRAY_PLUGIN_DATA_DIR"] = str(pdir)
        self.proc = subprocess.Popen(
            [
                str(REPO / "venv/bin/python"),
                str(REPO / "bundled_plugins/text-toolbox/text_toolbox.py"),
                "serve",
                "--no-open",
                "--port",
                str(self.port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import urllib.request

        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=1)
                return f"http://127.0.0.1:{self.port}"
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("toolbox 服务启动超时")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)


# ---------------------------------------------------------------- 判据收集
@dataclass
class Check:
    group: str
    case: str
    round_: int
    ok: bool
    detail: str = ""


@dataclass
class Ctx:
    page: object
    tb_url: str
    app_url: str
    scale: str
    round_: int
    checks: list = field(default_factory=list)

    def check(self, case: str, ok: bool, detail: str = ""):
        self.checks.append(
            Check(self.group_name, case, self.round_, bool(ok), str(detail)[:200])
        )
        return ok


# ---------------------------------------------------------------- CDN 策略
async def apply_cdn(page, mode: str):
    if mode == "normal":
        return
    # 注意 playwright glob：* 不跨 /，必须 ** 才能匹配整段路径（曾致拦截全未命中）
    domains = [
        "**cdn.jsdelivr.net/**",
        "**cdnjs.cloudflare.com/**",
        "**unpkg.com/**",
    ]

    async def handler(route, mode=mode):
        if mode == "blocked":
            await route.abort()
        else:  # hang：挂起足够久，页面必须靠自身超时降级
            await asyncio.sleep(20)
            try:
                await route.abort()
            except Exception:
                pass

    for d in domains:
        await page.route(d, handler)


# ---------------------------------------------------------------- 入口
GROUPS = {}


def group(name):
    def deco(fn):
        GROUPS[name] = fn
        return fn

    return deco


async def main_async(args):
    from playwright.async_api import async_playwright

    tmp = Path(tempfile.mkdtemp(prefix="zt-selftest-"))
    print(f"[selftest] 临时目录 {tmp}")
    app = AppServer(tmp, "medium")
    tb = ToolboxServer(tmp)
    app_url = app.start()
    tb_url = tb.start()
    print(f"[selftest] app={app_url} toolbox={tb_url}")

    all_checks: list[Check] = []
    scales = ["small", "medium", "large"]
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=CHROME, args=["--no-sandbox"]
            )
            for r in range(1, args.rounds + 1):
                scale = scales[(r - 1) % len(scales)]
                for gname in args.groups:
                    gfn = GROUPS[gname]
                    for cdn_mode in getattr(gfn, "cdn_modes", ["normal"]):
                        page = await browser.new_page(viewport={"width": 1100, "height": 800})
                        await apply_cdn(page, cdn_mode)
                        ctx = Ctx(page, tb_url, app_url, scale, r)
                        ctx.group_name = f"{gname}[{cdn_mode}]"
                        errs: list[str] = []
                        page.on("pageerror", lambda e: errs.append(str(e)[:100]))
                        t0 = time.monotonic()
                        try:
                            await asyncio.wait_for(
                                gfn(ctx, scale), timeout=getattr(gfn, "timeout", 120)
                            )
                        except Exception as e:
                            ctx.check("!!GROUP-CRASH", False, str(e)[:150])
                        dt = time.monotonic() - t0
                        if errs:
                            ctx.check("console-pageerror", False, "; ".join(errs[:2]))
                        all_checks.extend(ctx.checks)
                        await page.close()
                        ok_n = sum(1 for c in ctx.checks if c.ok)
                        print(
                            f"[round{r} {scale}] {ctx.group_name}: {ok_n}/{len(ctx.checks)} 通过 ({dt:.1f}s)"
                        )
            await browser.close()
    finally:
        tb.stop()
        app.stop()

    fail = [c for c in all_checks if not c.ok]
    print(f"\n===== 自测汇总：{len(all_checks) - len(fail)}/{len(all_checks)} 通过 =====")
    for c in fail:
        print(f"  ✗ [{c.group}] r{c.round_} {c.case} :: {c.detail}")
    out = REPO / "tools/selftest/report-last.json"
    out.write_text(
        json.dumps(
            [c.__dict__ for c in all_checks], ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    print(f"报告: {out}")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--groups", default="", help="逗号分隔；缺省=全部已注册")
    args = ap.parse_args()
    # 场景注册：exec 共享命名空间（避免 __main__ 双导入陷阱；场景文件用 group/Ctx 等）
    here = Path(__file__).parent
    ns = {"group": group, "Ctx": Ctx, "apply_cdn": apply_cdn, "REPO": REPO, "__name__": "scenarios"}
    for f in sorted(here.glob("scenarios_*.py")):
        exec(compile(f.read_text(encoding="utf-8"), str(f), "exec"), ns)
    args.groups = [g for g in (args.groups or ",".join(GROUPS)).split(",") if g]
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
