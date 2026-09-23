import datetime
import logging
import time

from PySide6.QtCore import QThread, Signal

from zentray.config import ARCHIVE_DIR, DATA_DIR
from zentray.core.repository import TaskRepository
from zentray.services.ai_review import AIReviewService
from zentray.services.notification import NotificationClient

logger = logging.getLogger(__name__)


class NightlyJobWorker(QThread):
    """
    调度：每日计划 + 每日复盘（各自开关与时间）。

    触发规则见 zentray.workers.ai_schedule：
    - 到点或过点后补跑（不要求 hour 全等）
    - 每日每 job 一次；状态落盘防重启重复
    - 修改触发时刻后允许同日按新时刻再跑
    """

    job_completed = Signal(str, str)  # title, message

    def __init__(self, task_repo: TaskRepository):
        super().__init__()
        self.is_running = True
        self.task_repo = task_repo
        # 兼容旧属性名（测试/调试）；以 state 文件为准
        self.last_plan_date = None
        self.last_review_date = None

    def run(self):
        from zentray.core.holidays import should_skip_auto_review
        from zentray.services.settings_manager import SettingsManager
        from zentray.workers import ai_schedule as sched

        state = sched.load_state()
        self.last_plan_date = state.last_plan_date
        self.last_review_date = state.last_review_date
        logger.info(
            "AI 调度 worker 循环启动 last_plan=%s last_review=%s",
            state.last_plan_date,
            state.last_review_date,
        )

        while self.is_running:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # 每次迭代重新读设置（保存设置后无需重启 worker）
            settings = SettingsManager()
            ai = settings.ai
            plan = ai.plan
            review = ai.review

            state = sched.sync_trigger_keys(
                state,
                plan_hour=int(plan.trigger_hour),
                plan_minute=int(plan.trigger_minute),
                review_hour=int(review.trigger_hour),
                review_minute=int(review.trigger_minute),
            )
            self.last_plan_date = state.last_plan_date
            self.last_review_date = state.last_review_date

            # —— 每日计划 ——
            if sched.should_fire_job(
                now,
                enabled=bool(plan.enabled),
                last_date=state.last_plan_date,
                trigger_hour=int(plan.trigger_hour),
                trigger_minute=int(plan.trigger_minute),
            ):
                if should_skip_auto_review(
                    now.date(),
                    skip_weekends=bool(plan.skip_weekends),
                    skip_holidays=bool(plan.skip_holidays),
                ):
                    state.last_plan_date = today_str
                    self.last_plan_date = today_str
                    sched.save_state(state)
                    logger.info("每日计划已跳过（周末/节假日）: %s", today_str)
                else:
                    logger.info(
                        "触发每日计划 @%s (设定 %02d:%02d)",
                        now.strftime("%H:%M"),
                        int(plan.trigger_hour),
                        int(plan.trigger_minute),
                    )
                    self._run_plan(today_str)
                    state.last_plan_date = today_str
                    self.last_plan_date = today_str
                    sched.save_state(state)

            # —— 每日复盘 ——
            if sched.should_fire_job(
                now,
                enabled=bool(review.enabled),
                last_date=state.last_review_date,
                trigger_hour=int(review.trigger_hour),
                trigger_minute=int(review.trigger_minute),
            ):
                if should_skip_auto_review(
                    now.date(),
                    skip_weekends=bool(review.skip_weekends),
                    skip_holidays=bool(review.skip_holidays),
                ):
                    state.last_review_date = today_str
                    self.last_review_date = today_str
                    sched.save_state(state)
                    logger.info("每日复盘已跳过（周末/节假日）: %s", today_str)
                else:
                    logger.info(
                        "触发每日复盘 @%s (设定 %02d:%02d)",
                        now.strftime("%H:%M"),
                        int(review.trigger_hour),
                        int(review.trigger_minute),
                    )
                    self._run_review(today_str)
                    state.last_review_date = today_str
                    self.last_review_date = today_str
                    sched.save_state(state)

            for _ in range(60):
                if not self.is_running:
                    break
                time.sleep(1)

    def _run_plan(self, today_str: str):
        try:
            ok = execute_daily_plan(today_str, self.task_repo)
            if ok:
                self.job_completed.emit("每日计划", "今日计划已生成。")
            else:
                self.job_completed.emit(
                    "每日计划",
                    "计划已执行，推送可能失败；请查看本地 reviews/。",
                )
        except Exception as e:
            logger.exception("Daily plan error: %s", e)

    def _run_review(self, today_str: str):
        try:
            ok = execute_nightly_review(today_str, self.task_repo)
            if ok:
                self.job_completed.emit("每日复盘", "复盘已生成。")
            else:
                self.job_completed.emit(
                    "每日复盘",
                    "复盘已执行，推送可能失败；请查看本地 reviews/。",
                )
        except Exception as e:
            logger.exception("Nightly review error: %s", e)

    def stop(self):
        self.is_running = False
        self.wait()


def _next_report_filename(kind: str, today_str: str) -> tuple[str, int]:
    """
    同一天可多次计划/复盘，用自增序号区分。
    返回 (filename, seq)。
    plan  → plan-YYYY-MM-DD.md / plan-YYYY-MM-DD-2.md
    review→ review-YYYY-MM-DD.md / review-YYYY-MM-DD-2.md
            （兼容旧名 YYYY-MM-DD.md 计为 #1）
    """
    reviews = DATA_DIR / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    if kind == "plan":
        base = f"plan-{today_str}"
        legacy = None
    else:
        base = f"review-{today_str}"
        legacy = f"{today_str}.md"

    existing = 0
    for p in reviews.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if legacy and name == legacy:
            existing = max(existing, 1)
            continue
        if name == f"{base}.md":
            existing = max(existing, 1)
            continue
        # base-N.md
        prefix = f"{base}-"
        if name.startswith(prefix) and name.endswith(".md"):
            mid = name[len(prefix) : -3]
            if mid.isdigit():
                existing = max(existing, int(mid))
    seq = existing + 1
    if seq <= 1:
        return f"{base}.md", 1
    return f"{base}-{seq}.md", seq


def _notify_and_save(
    title: str,
    report: str,
    *,
    save_local: bool,
    filename: str,
) -> bool:
    if save_local:
        reviews = DATA_DIR / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        path = reviews / filename
        try:
            path.write_text(report, encoding="utf-8")
        except OSError as e:
            logger.warning("save review failed: %s", e)

    client = NotificationClient.from_settings()
    result = client.send(title, report)
    # 应用弹窗由 job_completed 信号触发托盘通知
    return result.get("status") == "ok" or result.get("app_popup")


def execute_daily_plan(today_str: str, task_repo: TaskRepository) -> bool:
    """生成每日计划。"""
    from zentray.services.settings_manager import SettingsManager

    tasks = task_repo.find_all()
    lines = []
    for t in tasks:
        lines.append(
            f"- [{t.priority}] {t.title} "
            f"(进度 {getattr(t, 'progress', 0)}%, 截止 {t.deadline or '无'})"
        )
    pending = "\n".join(lines) if lines else "当前没有活跃任务。"

    prompt = (
        f"今天是 {today_str}。以下是我当前的活跃待办：\n{pending}\n\n"
        f"请为我制定一份「今日计划」。"
    )
    ai_reply = AIReviewService.generate_summary(prompt, kind="plan")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    style_name = SettingsManager().ai.plan.active_style().name
    report = f"# 📅 ZenTray 每日计划 ({today_str})\n\n"
    report += f"> ⏱️ 生成时间：{now}\n\n"
    if ai_reply:
        report += f"## 🧭 AI 计划（{style_name}）\n{ai_reply}\n\n"
    else:
        report += "## 🧭 AI 计划\n（生成失败或未配置 API Key）\n\n"
    report += "## 📋 当前任务快照\n" + pending + "\n"

    save_local = SettingsManager().ai.plan.save_local
    filename, seq = _next_report_filename("plan", today_str)
    ok = _notify_and_save(
        f"每日计划 {today_str}",
        report,
        save_local=save_local,
        filename=filename,
    )
    try:
        from zentray.services.activity_log import log_event

        log_event(
            "ai",
            "plan",
            f"{today_str}-计划-#{seq}",
            "已生成" if ai_reply else "生成失败或未配置",
            meta={"file": filename, "date": today_str, "seq": seq, "kind": "plan"},
        )
    except Exception:
        pass
    return ok


def execute_nightly_review(today_str: str, task_repo: TaskRepository) -> bool:
    """生成每日复盘（兼容旧入口名）。"""
    from zentray.services.settings_manager import SettingsManager

    now_time_precise = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_file = ARCHIVE_DIR / f"{today_str}.log"
    log_content = ""
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            log_content = f.read()

    tasks = task_repo.find_all()
    high_tasks = [t for t in tasks if t.priority == "high"]
    pending_str = "\n".join(
        [f"- [{t.category}] {t.title} (Deadline: {t.deadline})" for t in high_tasks]
    )

    prompt = (
        f"以下是我今天（{today_str}）的待办执行归档记录：\n"
        f"{log_content if log_content else '今天一条都没做，烂透了。'}\n\n"
        f"以下是明天死线迫在眉睫的紧急高危任务：\n"
        f"{pending_str if pending_str else '暂无紧急任务。'}\n\n"
        f"请为我生成一份每日总结与明日规划。"
    )

    ai_reply = AIReviewService.generate_summary(prompt, kind="review")

    report = f"# 📅 ZenTray 禅定复盘 ({today_str})\n\n"
    report += f"> ⏱️ 生成时间：{now_time_precise} (防折叠标识)\n\n"

    style_name = SettingsManager().ai.review.active_style().name
    if ai_reply:
        report += f"## 🤖 AI 教练锐评（{style_name}）\n{ai_reply}\n\n"
    else:
        report += "## 🤖 AI 教练锐评\n（生成失败或未配置 API Key）\n\n"

    report += "## 📌 高优先任务\n"
    report += (pending_str or "暂无") + "\n"

    save_local = SettingsManager().ai.review.save_local
    filename, seq = _next_report_filename("review", today_str)
    ok = _notify_and_save(
        f"每日复盘 {today_str}",
        report,
        save_local=save_local,
        filename=filename,
    )
    try:
        from zentray.services.activity_log import log_event

        log_event(
            "ai",
            "review",
            f"{today_str}-复盘-#{seq}",
            "已生成" if ai_reply else "生成失败或未配置",
            meta={"file": filename, "date": today_str, "seq": seq, "kind": "review"},
        )
    except Exception:
        pass
    return ok
