"""完成动画卡顿回归（feature/complete-anim-lag）。

症状：Ubuntu 上点击「完成」后勾选动画卡顿。测量定位（150 任务，rAF 采样）：
- 动画启动延迟 57-116ms（等 POST /done 返回 + Message 渲染后才起 celebrateCard）
- 点击后 520ms 的 reload 造成 ~313ms 主线程冻结（623→936ms 无帧）：
  TransitionGroup 的 zt-list CSS 过渡与 runFlip 的 GSAP Flip 同驱 125 张卡的
  transform 互相打架（move 类残留 1.4s+），历史卡 key 含索引（h:...:i）导致
  每次完成全量重建隐藏的历史卡（17 进 17 出 + 300 次 childList 变更）。

修复约定（本文件防回退）：
1. 列表动画唯一来源是 GSAP（celebrateCard/runFlip），不得再挂 TransitionGroup
   CSS 过渡双系统；
2. 历史卡 key 必须内容稳定（禁止索引），防每次 reload 全量重建；
3. styles.css 不得回流 .zt-list-* 过渡（双驱动元凶）；
4. 完成动作乐观起动画：celebrateCard 先于持久化请求（启动延迟根因）。

live 用例（有 /usr/bin/google-chrome 或 playwright chromium 时才跑）：
断言点击→动画启动先于 POST /done 响应、无 zt-list-move、点击后 2.5s 内
无 >100ms 长帧、最大帧 <150ms。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TASKLIST = (_ROOT / "web" / "src" / "views" / "TaskList.vue").read_text(encoding="utf-8")
_STYLES = (_ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")


def test_list_animation_single_source_no_transition_group():
    # TransitionGroup 的 CSS move/leave 过渡与 runFlip 的 GSAP Flip 同驱同一批
    # 卡片 transform：逐帧样式重算互相重启，125 卡时点击后 300ms 级冻结
    assert "<TransitionGroup" not in _TASKLIST, (
        "任务列表不得用 TransitionGroup（与 runFlip/celebrateCard 的 GSAP 双驱动，"
        "列表动画统一走 GSAP）"
    )


def test_history_key_stable_not_indexed():
    # key 含索引（:i）时每次完成（归档新条目前插）全体历史卡销毁重建，
    # 即使 display:none 也产生数百次 DOM 变更（长帧直接来源）
    assert "h:${a.archived_at}:${i}" not in _TASKLIST, "历史卡 key 不得含索引"
    assert "h:${a.archived_at}:${a.status}" in _TASKLIST, "历史卡 key 须为内容稳定键"


def test_styles_no_zt_list_transitions():
    assert ".zt-list-" not in _STYLES, (
        "styles.css 不得回流 .zt-list-* 过渡（TransitionGroup 已移除，死代码）"
    )


def test_celebrate_before_persist():
    # 完成动作须乐观起动画：celebrateCard 在持久化请求 resolve 之前启动，
    # 否则点击→动画有 57-116ms 可感启动延迟（POST 20-40ms + Message 渲染）
    seg = _TASKLIST[_TASKLIST.index("function optimisticFinish") :]
    seg = seg[: seg.index("\n}", 0)]
    assert seg.index("celebrateCard") < seg.index("await action()"), (
        "optimisticFinish 须先 celebrateCard 再 await 持久化"
    )
    # onDone 走乐观路径而非先 await markDone 再 finishAndRefresh
    ondone = _TASKLIST[_TASKLIST.index("async function onDone") :]
    ondone = ondone[: ondone.index("\n}\n")]
    assert "optimisticFinish" in ondone


def test_flip_simple_mode():
    # Flip 默认逐元素算全局矩阵：gsap 往列表临时插测量脚手架再拆（每卡一次
    # appendChild+回流），150 卡 reload = 368 次 childList 变更 + 250ms 级冻结。
    # simple 模式只用 getBoundingClientRect，位移类列表动画足够
    assert "Flip.getState(cards, { simple: true })" in _TASKLIST
    assert "simple: true" in _TASKLIST[_TASKLIST.index("Flip.from(state") :][:400]


def test_celebrate_suppresses_transform_transition():
    # .task-card-item 基类带 transition: transform（hover 升起），庆祝补间逐帧写
    # transform 会与其互相重启插值，软件合成下整段掉帧（p95 33ms → 16.8ms）
    seg = _TASKLIST[_TASKLIST.index("function celebrateCard") :]
    seg = seg[: seg.index("\n}\n", 10)]
    assert "transition: 'none'" in seg, "celebrateCard 须在动画期间抑制基类 transform 过渡"


# ---------------- live 浏览器帧采样（环境不备则 skip） ----------------

_CHROME_CANDIDATES = ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable")


def _chrome_path() -> str | None:
    for p in _CHROME_CANDIDATES:
        if Path(p).is_file():
            return p
    return shutil.which("google-chrome") or shutil.which("chromium")


def _dist_ready() -> bool:
    return (_ROOT / "web" / "dist" / "index.html").is_file()


def test_complete_animation_smooth_live():
    if not (_dist_ready() and _chrome_path()):
        pytest.skip("无 web/dist 或 Chrome，跳过 live 帧采样")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright 未安装")

    from zentray import config
    import zentray.services.settings_manager as sm
    from zentray.api.handlers import ApiContext, set_api_context
    from zentray.api.server import LocalApiServer
    from zentray.core.models import Task
    from zentray.core.scheduler import Scheduler
    from zentray.repositories.file_periodic_repository import (
        FilePeriodicTemplateRepository,
    )
    from zentray.repositories.file_repository import FileTaskRepository
    from zentray.services.task_service import TaskService

    from zentray.api import handlers as api_handlers

    # 数据目录切临时目录（绝不可触真实 ~/.local/share/ZenTray）
    tmp = Path(tempfile.mkdtemp(prefix="zt-anim-test-"))
    saved = (
        config.DATA_DIR,
        config.ACTIVE_TASKS_FILE,
        config.PERIODIC_TEMPLATES_FILE,
        config.ARCHIVE_DIR,
        sm.SETTINGS_FILE,
        sm.DATA_DIR,
        sm.SettingsManager._instance,
        api_handlers._ctx,
    )
    config.DATA_DIR = tmp
    config.ACTIVE_TASKS_FILE = tmp / "active_tasks.json"
    config.PERIODIC_TEMPLATES_FILE = tmp / "periodic_templates.json"
    config.ARCHIVE_DIR = tmp / "archive"
    config.ARCHIVE_DIR.mkdir(parents=True)
    sm.SETTINGS_FILE = tmp / "settings.json"
    sm.DATA_DIR = tmp
    sm.SettingsManager._instance = None
    try:
        repo = FileTaskRepository(
            active_file=config.ACTIVE_TASKS_FILE, archive_dir=config.ARCHIVE_DIR
        )
        trepo = FilePeriodicTemplateRepository(filepath=config.PERIODIC_TEMPLATES_FILE)
        svc = TaskService(repo, trepo, Scheduler())
        set_api_context(ApiContext(task_service=svc))
        repo.save_all(
            [
                Task(title=f"压测任务 {i:03d}", category="工作", details="d" * 30)
                for i in range(120)
            ]
        )
        # 预置历史归档，验证索引 key 重建路径
        for i in range(20):
            repo.archive(
                Task(title=f"历史 {i}", category="工作", priority="low"), "DONE"
            )
        srv = LocalApiServer(host="127.0.0.1", port=0)
        url = srv.start()
        try:
            _run_browser_assertions(url, sync_playwright)
        finally:
            srv.stop()
    finally:
        (
            config.DATA_DIR,
            config.ACTIVE_TASKS_FILE,
            config.PERIODIC_TEMPLATES_FILE,
            config.ARCHIVE_DIR,
            sm.SETTINGS_FILE,
            sm.DATA_DIR,
            sm.SettingsManager._instance,
            api_handlers._ctx,
        ) = saved
        shutil.rmtree(tmp, ignore_errors=True)


_PAGE_SETUP = """
() => {
  window.__zt = { frames: [], clickAt: null, animStart: null, doneEnd: null, moveSeen: false };
  const z = window.__zt;
  function tick(t) { z.frames.push(t); requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.name.includes('/done')) z.doneEnd = e.responseEnd;
    }
  }).observe({ type: 'resource', buffered: true });
  const card = document.querySelector('.task-card-item');
  new MutationObserver((muts) => {
    if (z.animStart == null && muts.some((m) => m.attributeName === 'style')) {
      z.animStart = performance.now();
    }
  }).observe(card, { attributes: true, attributeFilter: ['style'] });
  // zt-list-move 不得再出现（TransitionGroup 双驱动）
  new MutationObserver((muts) => {
    for (const m of muts) {
      if ((m.target.className || '').includes('zt-list-move')) z.moveSeen = true;
    }
  }).observe(document.querySelector('.task-card-list'),
             { subtree: true, attributes: true, attributeFilter: ['class'] });
  const btns = [...document.querySelectorAll('button')]
    .filter((b) => b.textContent.trim() === '完成');
  btns[btns.length - 1].addEventListener(
    'click', () => { z.clickAt = performance.now(); }, { once: true });
}
"""

_COLLECT = """
() => {
  const z = window.__zt;
  const t0 = z.clickAt;
  // 动画窗口：celebrate 离场 0.46s + 邻居让位 0.5s，550ms 内须全程流畅
  const anim = [];
  const all = [];
  for (let i = 1; i < z.frames.length; i++) {
    if (z.frames[i - 1] < t0) continue;
    const d = z.frames[i] - z.frames[i - 1];
    all.push(d);
    if (z.frames[i] <= t0 + 550) anim.push(d);
  }
  return {
    animStart: z.animStart, clickAt: t0, doneEnd: z.doneEnd, moveSeen: z.moveSeen,
    animLong80: anim.filter((d) => d > 80).length,
    max: all.length ? Math.max(...all) : 0,
  };
}
"""


def _run_browser_assertions(url, sync_playwright) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=_chrome_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url + "/#/tasks")
        page.wait_for_selector(".task-card-item", timeout=15000)
        page.wait_for_timeout(1500)
        page.evaluate(_PAGE_SETUP)
        page.locator("button:has-text('完成')").last.click()
        page.wait_for_timeout(3200)
        res = page.evaluate(_COLLECT)
        browser.close()

    assert res["clickAt"] is not None, "未捕获点击"
    assert res["animStart"] is not None, "完成动画未启动"
    # 乐观动画：动画启动须先于 POST /done 响应（修复前始终晚于响应）
    assert res["animStart"] <= res["doneEnd"], (
        f"动画启动({res['animStart']:.0f}ms) 晚于 POST /done 响应({res['doneEnd']:.0f}ms)："
        "完成动作未乐观起动画"
    )
    assert not res["moveSeen"], "zt-list-move 出现：TransitionGroup CSS 过渡回流"
    # 动画窗口内不得有 >80ms 长帧（修复前 p95 33ms、窗口内 110-183ms 长帧）
    assert res["animLong80"] == 0, (
        f"完成动画窗口(550ms)内出现 {res['animLong80']} 个 >80ms 长帧"
    )
    # 全程最大帧：基线 183-333ms（TransitionGroup×Flip 双驱动 + gsap 矩阵脚手架
    # 368 次插拔），修复后仅剩单次数据置换帧（≈80-150ms）
    assert res["max"] < 180, f"最大帧间隔 {res['max']:.0f}ms（基线 183-333ms）"
