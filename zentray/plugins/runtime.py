"""插件进程执行与进度信号。"""
from __future__ import annotations

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
from zentray.plugins.loader import LoadedPlugin
from zentray.plugins.models import PluginType
from zentray.plugins.protocol import format_tray_text, parse_stdout_line

logger = logging.getLogger(__name__)


class PluginRuntime(QObject):
    """同一时间仅一个 script；service 启停为短命令。"""

    log_line = Signal(str)  # 托盘文案
    progress = Signal(int, int, str)  # current, total, message
    script_finished = Signal(str, bool, str)  # plugin_id, ok, summary
    busy_changed = Signal(bool)

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
    ) -> bool:
        """异步启动 script。返回 False 表示未启动（调用方自行提示原因）。"""
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
            args=(plugin,),
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

    def _run_script_thread(self, plugin: LoadedPlugin) -> None:
        m = plugin.manifest
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = self._runs_dir / f"{stamp}_{m.id}.log"
        last_json = self._runs_dir / "last.json"

        cmd = [str(m.entry_path), *m.args]
        env = os.environ.copy()
        env.update(m.env)
        ok = False
        summary = ""
        lines: List[str] = []

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
                    tray = format_tray_text(m.name, parsed)
                    self.log_line.emit(tray)
                    if parsed.kind == "progress" and parsed.progress:
                        p = parsed.progress
                        self.progress.emit(p.current, p.total, p.message)

                code = self._proc.poll()
                if code is None:
                    code = self._proc.wait()
                if summary != "超时":
                    ok = code == 0
                    summary = "成功" if ok else f"失败(code={code})"
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
            try:
                import json

                last_json.write_text(
                    json.dumps(
                        {
                            "id": m.id,
                            "name": m.name,
                            "ok": ok,
                            "summary": summary,
                            "log": str(log_path),
                            "time": datetime.now().isoformat(timespec="seconds"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
            self.script_finished.emit(m.id, ok, summary)
