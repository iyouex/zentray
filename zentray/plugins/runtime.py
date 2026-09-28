"""插件进程执行与进度信号。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Signal

from zentray.config import DATA_DIR
from zentray.core.models import Task
from zentray.plugins.loader import LoadedPlugin
from zentray.plugins.models import PluginType, resolve_param_values


def _read_param_presets(pid: str) -> dict:
    """读参数预设；设置不可用时静默回落空。"""
    try:
        from zentray.services.settings_manager import SettingsManager

        return SettingsManager().ops.param_presets.get(pid) or {}
    except Exception:
        return {}
from zentray.plugins.protocol import ParsedLine, format_tray_text, parse_stdout_line

logger = logging.getLogger(__name__)


class PluginRuntime(QObject):
    """同一时间仅一个 script；service 启停为短命令。"""

    log_line = Signal(str)  # 托盘文案
    progress = Signal(int, int, str)  # current, total, message
    script_finished = Signal(str, bool, str)  # plugin_id, ok, summary
    busy_changed = Signal(bool)
    # 完整运行报告（主线程做通知/写回/activity log）：
    # {id, name, ok, summary, result_text, trigger, task_id, log, time}
    run_report = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._runs_dir = DATA_DIR / "ops_runs"

    @property
    def is_busy(self) -> bool:
        return self._busy

    def run_script(
        self,
        plugin: LoadedPlugin,
        *,
        pomodoro_active: bool = False,
        task: Optional[Task] = None,
        trigger: str = "manual",
        param_values: Optional[List[str]] = None,
    ) -> bool:
        """异步启动 script。返回 False 表示未启动（调用方自行提示原因）。

        param_values: 命名入参的值（按 manifest.params 声明顺序）；
        None 时回落各参数 default。
        """
        m = plugin.manifest
        if m.type != PluginType.SCRIPT:
            logger.error("run_script 仅用于 script: %s", m.id)
            return False
        if pomodoro_active:
            return False
        with self._lock:
            if self._busy:
                return False
            self._busy = True
        self.busy_changed.emit(True)

        thread = threading.Thread(
            target=self._run_script_thread,
            args=(plugin, task, trigger, param_values),
            name=f"ops-script-{m.id}",
            daemon=True,
        )
        thread.start()
        return True

    def service_cmd(
        self,
        plugin: LoadedPlugin,
        action: str,
        *,
        pomodoro_active: bool = False,
    ) -> tuple[bool, str]:
        """同步执行 service 的 start|stop|status（短命令）。

        返回 (ok, detail)，detail 为可直接展示的短文案。
        # ponytail: 服务命令不 emit log_line——托盘抢占(_ops_active)只由
        # script 生命周期（script_finished）复位，服务若参与会永久卡死轮播。
        """
        action = (action or "").strip().lower()
        if action not in ("start", "stop", "status"):
            return False, f"未知命令: {action}"
        if plugin.manifest.type != PluginType.SERVICE:
            return False, "仅支持 service 类型插件"
        if pomodoro_active and action in ("start", "stop"):
            return False, "番茄钟进行中，无法操作服务"
        with self._lock:
            if self._busy:
                return False, "脚本运行中，请稍候"

        m = plugin.manifest
        cmd = [str(m.entry_path), action, *m.args]
        env = os.environ.copy()
        env.update(m.env)
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(m.work_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except Exception as e:
            logger.exception("service 命令失败")
            return False, f"{m.name}: {e}"[:80]

        out = (completed.stdout or "").strip()
        first = out.splitlines()[0].strip() if out else ""
        if action == "status":
            status = first.lower() if first.lower() in (
                "running",
                "stopped",
                "unknown",
            ) else ("running" if completed.returncode == 0 else "stopped")
            return completed.returncode == 0, status
        ok = completed.returncode == 0
        return ok, f"{action} " + ("成功" if ok else "失败")

    @staticmethod
    def _preset_or_default(m, param) -> str:
        """入参缺省值：预设（settings.ops.param_presets）> manifest default。"""
        return resolve_param_values([param], _read_param_presets(m.id))[0]

    def _run_script_thread(
        self,
        plugin: LoadedPlugin,
        task: Optional[Task],
        trigger: str,
        param_values: Optional[List[str]] = None,
    ) -> None:
        m = plugin.manifest
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{stamp}_{m.id}"
        started_at = datetime.now().isoformat(timespec="seconds")
        log_path = self._runs_dir / f"{run_id}.log"
        meta_json = self._runs_dir / f"{run_id}.json"
        last_json = self._runs_dir / "last.json"

        values = list(param_values) if param_values is not None else [
            self._preset_or_default(m, p) for p in m.params
        ]
        cmd = [str(m.entry_path), *m.args, *values]
        env = os.environ.copy()
        env.update(m.env)
        # 任务上下文最后注入（动态覆盖静态）；触发来源始终注入
        if task is not None:
            env["ZENTRAY_TASK_ID"] = task.id
            env["ZENTRAY_TASK_TITLE"] = task.title
            if task.details:
                env["ZENTRAY_TASK_DETAILS"] = task.details
            if task.category:
                env["ZENTRAY_TASK_CATEGORY"] = task.category
            if task.priority:
                env["ZENTRAY_TASK_PRIORITY"] = task.priority
            if task.deadline:
                env["ZENTRAY_TASK_DEADLINE"] = task.deadline
        env["ZENTRAY_TRIGGER"] = trigger
        ok = False
        summary = ""
        lines: List[str] = []
        last_result: Optional[ParsedLine] = None

        try:
            self.log_line.emit(f"⚡ 开始 {m.name}"[:50])
            with open(log_path, "w", encoding="utf-8") as logf:
                logf.write(f"$ {' '.join(cmd)}\n")
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(m.work_path),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                deadline = None
                if m.timeout_sec and m.timeout_sec > 0:
                    deadline = time.monotonic() + m.timeout_sec

                assert self._proc.stdout is not None
                while True:
                    if deadline and time.monotonic() > deadline:
                        self._proc.terminate()
                        try:
                            self._proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            self._proc.kill()
                        summary = "超时"
                        logf.write("\n[TIMEOUT]\n")
                        ok = False
                        break

                    line = self._proc.stdout.readline()
                    if line == "" and self._proc.poll() is not None:
                        break
                    if not line:
                        time.sleep(0.05)
                        continue
                    logf.write(line)
                    lines.append(line)
                    parsed = parse_stdout_line(line)
                    if parsed.kind == "result":
                        last_result = parsed  # 最后一个 RESULT 行生效
                    tray = format_tray_text(m.name, parsed)
                    self.log_line.emit(tray)
                    if parsed.kind == "progress" and parsed.progress:
                        p = parsed.progress
                        self.progress.emit(p.current, p.total, p.message)

                code = self._proc.poll()
                if code is None:
                    code = self._proc.wait()
                if summary != "超时":
                    # 成败判定（v2）：退出码非 0 一票否决；RESULT fail 一票
                    # 否决（即使 exit 0）；无 RESULT 行退化为纯退出码。
                    ok = code == 0
                    if last_result is not None and last_result.result_ok is False:
                        ok = False
                        summary = f"失败(RESULT: {last_result.text})"
                    elif ok:
                        if last_result is not None and last_result.text != "成功":
                            summary = last_result.text
                        else:
                            summary = "成功"
                    else:
                        summary = f"失败(code={code})"
        except Exception as e:
            logger.exception("脚本执行异常 %s", m.id)
            ok = False
            summary = str(e)[:80]
            self.log_line.emit(f"⚡ 错误: {summary}"[:50])
        finally:
            self._proc = None
            with self._lock:
                self._busy = False
            self.busy_changed.emit(False)
            report = {
                "id": m.id,
                "name": m.name,
                "run_id": run_id,
                "started_at": started_at,
                "ok": ok,
                "summary": summary,
                "result_text": last_result.text if last_result is not None else "",
                "trigger": trigger,
                "task_id": task.id if task is not None else "",
                "log": str(log_path),
                "time": datetime.now().isoformat(timespec="seconds"),
            }
            for target in (last_json, meta_json):
                try:
                    target.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            self.script_finished.emit(m.id, ok, summary)
            self.run_report.emit(report)
