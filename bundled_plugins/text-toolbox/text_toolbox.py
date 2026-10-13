#!/usr/bin/env python3
"""文本工具箱 —— ZenTray service 插件入口（纯标准库）。

动作（service 协议，见 docs/plugins/PLUGIN_SPEC.md §5）：
  start    后台启动本地 Web 服务（detach），就绪后自动打开浏览器，快速返回
  stop     停止服务并释放端口
  status   stdout 首行 running | stopped | unknown

其它子命令：
  serve    前台运行服务（调试/自测用，--no-open 抑制浏览器）
  selftest 服务级自测（不起浏览器）

服务只做：127.0.0.1 绑定 + 端口占用重试（默认 18767，最多 +10）+ 静态页托管。
HTTP 端点全部只读：GET /（页面）、/healthz、/api/tasks（读 active_tasks.json
做只读投影，供万年历「当日任务」展示；读取失败返回 []）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PLUGIN_ID = "text-toolbox"
HERE = Path(__file__).resolve().parent
PORT_TRIES = 10
# 标签页心跳超时：页面每 5s ping /tab-heartbeat，超过该时长无 ping 视为标签页已关闭
TAB_STALE_AFTER = 15.0
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
    "https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'"
)


def _default_port() -> int:
    try:
        return int(os.environ.get("TEXT_TOOLBOX_PORT", "18767"))
    except ValueError:
        return 18767


def _data_dir() -> Path:
    """状态目录：ZENTRAY_PLUGIN_DATA_DIR（运行时注入）> 用户数据目录兜底。"""
    base = os.environ.get("ZENTRAY_PLUGIN_DATA_DIR")
    p = (
        Path(base)
        if base
        else Path.home() / ".local/share/ZenTray/plugin_data" / PLUGIN_ID
    )
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_file() -> Path:
    return _data_dir() / "state.json"


def _read_state() -> dict:
    try:
        v = json.loads(_state_file().read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _write_state(d: dict) -> None:
    try:
        _state_file().write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _clear_state() -> None:
    try:
        _state_file().unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _port_open(port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def _is_running() -> tuple[bool, dict]:
    st = _read_state()
    pid, port = st.get("pid", 0), st.get("port", 0)
    if _pid_alive(pid) and port and _port_open(port):
        return True, st
    return False, st


def _open_browser(url: str) -> None:
    """启动时开一次；Linux 用 xdg-open（后台 detach），退化 webbrowser。"""
    xdg = shutil.which("xdg-open")
    if xdg:
        try:
            subprocess.Popen(
                [xdg, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        except OSError:
            pass
    import webbrowser

    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()


# ---------------------------------------------------------------- HTTP 服务


def _tasks_json() -> bytes:
    """ZenTray 活跃任务只读投影（万年历「当日任务」用）。

    数据源：DATA_DIR/active_tasks.json（DATA_DIR = ZENTRAY_PLUGIN_DATA_DIR 的
    上两级，运行时注入；无注入时回退 ~/.local/share/ZenTray）。
    """
    base = os.environ.get("ZENTRAY_PLUGIN_DATA_DIR")
    data_dir = (
        Path(base).parent.parent
        if base
        else Path.home() / ".local/share/ZenTray"
    )
    try:
        items = json.loads(
            (data_dir / "active_tasks.json").read_text(encoding="utf-8")
        )
        proj = [
            {
                "title": str(t.get("title") or ""),
                "deadline": str(t.get("deadline") or ""),
                "category": str(t.get("category") or ""),
                "reminder": t.get("reminder")
                if isinstance(t.get("reminder"), dict)
                else {},
            }
            for t in items
            if isinstance(t, dict)
        ]
        return json.dumps(proj, ensure_ascii=False).encode()
    except Exception:
        return b"[]"


def _build_handler(index_bytes: bytes):
    # 标签页心跳：页面每 5s ping /tab-heartbeat；start 命令经 /tab-alive 查询，
    # 已有活跃标签页则不重复新开。served_at 提供启动宽限（页面尚未加载完成的
    # 双击窗口期）。ponytail: 系统挂起等导致 ping 停滞后 start 会多开一页，
    # 需要精确感知时再换 named-window（window.open 复用同名窗口）方案。
    tab = {"last_seen": 0.0, "served_at": time.monotonic()}

    class Handler(BaseHTTPRequestHandler):
        server_version = "TextToolbox/0.1"
        protocol_version = "HTTP/1.1"

        def _send(
            self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, index_bytes)
            elif path == "/healthz":
                self._send(200, b"ok\n", "text/plain; charset=utf-8")
            elif path == "/api/tasks":
                self._send(200, _tasks_json(), "application/json; charset=utf-8")
            elif path == "/tab-heartbeat":
                tab["last_seen"] = time.monotonic()
                self._send(200, b"ok\n", "text/plain; charset=utf-8")
            elif path == "/tab-alive":
                # max_age 仅自测用（免 15s 真等）；只读参数，不影响安全性
                from urllib.parse import parse_qs, urlsplit

                try:
                    max_age = min(600.0, max(
                        0.0, float(parse_qs(urlsplit(self.path).query)
                                   .get("max_age", [""])[0])))
                except ValueError:
                    max_age = TAB_STALE_AFTER
                age = time.monotonic() - max(tab["last_seen"], tab["served_at"])
                self._send(200, json.dumps({"alive": age < max_age}).encode(),
                           "application/json; charset=utf-8")
            elif path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self._send(
                    404,
                    "404 Not Found".encode(),
                    "text/plain; charset=utf-8",
                )

        do_HEAD = do_GET  # noqa: N802

        def log_message(self, *args) -> None:  # 静默访问日志，防 server.log 膨胀
            pass

    return Handler


def cmd_serve(args) -> int:
    index_file = HERE / "index.html"
    try:
        index_bytes = index_file.read_bytes()
    except OSError as e:
        print(f"LOG 启动失败: 缺少 index.html ({e})", flush=True)
        return 1

    httpd = None
    bound = None
    for port in range(args.port, args.port + PORT_TRIES):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), _build_handler(index_bytes))
            bound = port
            break
        except OSError:
            continue
    if httpd is None:
        print(
            f"LOG 启动失败: 端口 {args.port}-{args.port + PORT_TRIES - 1} 均被占用",
            flush=True,
        )
        return 1

    url = f"http://127.0.0.1:{bound}/"
    _write_state({"pid": os.getpid(), "port": bound, "url": url,
                  "started_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    print(f"LOG 文本工具箱已启动 {url} (pid {os.getpid()})", flush=True)
    print(f"URL {url}", flush=True)

    if not args.no_open:
        _open_browser(url)

    def _stop(signum, frame):
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        httpd.serve_forever(poll_interval=0.2)
    finally:
        httpd.server_close()
        _clear_state()
        print("LOG 文本工具箱已停止", flush=True)
    return 0


# ---------------------------------------------------------------- start/stop/status


def cmd_start(args) -> int:
    running, st = _is_running()
    if running:
        url = st.get("url") or f"http://127.0.0.1:{st.get('port')}/"
        if args.no_open:
            print(f"LOG 已在运行 {url}", flush=True)
        else:
            # 显式点击即「打开给我看」：无论原标签页是否存活都跳转，
            # 新开或复用由浏览器决定。心跳接口保留仅作页面存活观测。
            print(f"LOG 已在运行 {url}，跳转浏览器", flush=True)
        print(f"URL {url}", flush=True)
        if not args.no_open:
            _open_browser(url)
        return 0

    _clear_state()  # 清理陈旧 state
    logfile = _data_dir() / "server.log"
    with open(logfile, "ab") as logf:
        proc = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "serve",
                "--port",
                str(args.port),
            ]
            + (["--no-open"] if args.no_open else []),
            stdout=logf,
            stderr=subprocess.STDOUT,
            cwd=str(HERE),
            start_new_session=True,  # 脱离 ZenTray 进程组，退出码立即返回
        )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break  # serve 进程已退出（多半是端口全被占）
        running, st = _is_running()
        if running:
            url = st.get("url") or f"http://127.0.0.1:{st.get('port')}/"
            print(f"LOG 文本工具箱已启动 {url} (pid {st.get('pid')})", flush=True)
            print(f"URL {url}", flush=True)
            return 0
        time.sleep(0.15)
    print("LOG 启动失败: 服务未在 10s 内就绪，详见 "
          f"{_data_dir() / 'server.log'}", flush=True)
    return 1


def cmd_stop(args) -> int:
    st = _read_state()
    pid, port = st.get("pid", 0), st.get("port", 0)
    if not _pid_alive(pid):
        _clear_state()
        print("LOG 服务未在运行", flush=True)
        return 0

    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"LOG 停止失败: {e}", flush=True)
        return 1

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    if _pid_alive(pid) and os.name != "nt":
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.3)

    released = not (port and _port_open(port))
    _clear_state()
    detail = f"端口 {port} 已释放" if (port and released) else ""
    print("LOG 文本工具箱已停止" + (f"，{detail}" if detail else ""), flush=True)
    return 0


def cmd_status(args) -> int:
    running, st = _is_running()
    if running:
        print("running", flush=True)
        print(f"URL {st.get('url') or f'http://127.0.0.1:{st.get('port')}/'}",
              flush=True)
        return 0
    pid = st.get("pid", 0)
    if _pid_alive(pid):  # 进程在但端口不通：状态不明
        print("unknown", flush=True)
        return 0
    _clear_state()
    print("stopped", flush=True)
    return 0


# ---------------------------------------------------------------- selftest


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(port: int, path: str = "/"):
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=5
        ) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)


def cmd_selftest(args) -> int:
    fails: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        line = f"[{mark}] {name}"
        if not cond and detail:
            line += f" — {detail}"
        print(line, flush=True)
        if not cond:
            fails.append(name)

    tmp = tempfile.mkdtemp(prefix="text-toolbox-selftest-")
    env = os.environ.copy()
    env["ZENTRAY_PLUGIN_DATA_DIR"] = tmp

    # --- A. 前台 serve：端口占用自动 +1、URL 行、页面锚点、healthz、404、SIGTERM 释放
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    held_port = holder.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "serve",
         "--port", str(held_port), "--no-open"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    lines: list[str] = []

    def _reader():
        for ln in proc.stdout:
            lines.append(ln.rstrip("\n"))

    rt = threading.Thread(target=_reader, daemon=True)
    rt.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if any(ln.startswith("URL ") for ln in lines):
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)

    url_lines = [ln for ln in lines if ln.startswith("URL ")]
    check("stdout 含 URL 行", bool(url_lines), f"stdout={lines}")
    port = None
    if url_lines:
        try:
            port = int(url_lines[0].rsplit(":", 1)[1].strip("/ "))
        except (ValueError, IndexError):
            pass
    check("端口被占自动 +1", port == held_port + 1,
          f"held={held_port} got={port}")
    check("stdout 含 LOG 行", any(ln.startswith("LOG ") for ln in lines))

    if port:
        code, body = _http_get(port, "/")
        check("GET / 返回 200", code == 200, f"code={code}")
        for tool in ("json", "sql", "diff", "time", "random", "crypto"):
            check(f"页面含区块锚点 data-tool=\"{tool}\"",
                  f'data-tool="{tool}"' in body)
        for anchor in ("time-seg", "ts-dir", "ts-unit-sel", "cal-tasks", "dt-in-slot",
                       "add-base-slot", "diff-a-slot", "diff-b-slot", "fmt-in-slot"):
            check(f"页面含交互锚点 id=\"{anchor}\"", f'id="{anchor}"' in body)
        code, body = _http_get(port, "/healthz")
        check("GET /healthz 返回 200", code == 200 and "ok" in body,
              f"code={code} body={body[:60]}")
        code, body = _http_get(port, "/api/tasks")
        check("GET /api/tasks 返回 JSON 数组", code == 200 and body.startswith("["),
              f"code={code} body={body[:40]}")
        code, body = _http_get(port, "/tab-alive")
        check("GET /tab-alive 启动宽限内 alive",
              code == 200 and '"alive": true' in body,
              f"code={code} body={body[:60]}")
        code, body = _http_get(port, "/tab-heartbeat")
        check("GET /tab-heartbeat 返回 200", code == 200 and "ok" in body,
              f"code={code} body={body[:40]}")
        code, body = _http_get(port, "/tab-alive?max_age=0")
        check("GET /tab-alive 零窗口判 stale",
              code == 200 and '"alive": false' in body,
              f"code={code} body={body[:60]}")
        code, _ = _http_get(port, "/no-such-path")
        check("GET 未知路径返回 404", code == 404, f"code={code}")

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    check("SIGTERM 后进程退出", proc.poll() is not None)
    if port:
        check("停止后端口已释放", not _port_open(port))
    holder.close()

    # --- B. start/status/stop 协议链路
    entry = str(Path(__file__).resolve())
    r = subprocess.run([entry, "start", "--no-open"],
                       capture_output=True, text=True, env=env, timeout=30)
    check("start 退出码 0", r.returncode == 0, r.stdout + r.stderr)
    r2 = subprocess.run([entry, "status"], capture_output=True, text=True,
                        env=env, timeout=15)
    first = r2.stdout.splitlines()[0].strip() if r2.stdout else ""
    check("status 首行 running", first == "running", f"first={first!r}")
    st = json.loads((Path(tmp) / "state.json").read_text())
    code, body = _http_get(st["port"], "/")
    check("start 后 GET / 返回 200", code == 200, f"code={code}")
    r3 = subprocess.run([entry, "stop"], capture_output=True, text=True,
                        env=env, timeout=15)
    check("stop 退出码 0", r3.returncode == 0, r3.stdout + r3.stderr)
    check("stop 后端口已释放", not _port_open(st["port"]))
    r4 = subprocess.run([entry, "status"], capture_output=True, text=True,
                        env=env, timeout=15)
    first4 = r4.stdout.splitlines()[0].strip() if r4.stdout else ""
    check("stop 后 status 首行 stopped", first4 == "stopped", f"first={first4!r}")

    print(f"\nselftest {'全部通过' if not fails else f'{len(fails)} 项失败'}: "
          f"{'/'.join(fails) if fails else 'ok'}", flush=True)
    return 1 if fails else 0


# ---------------------------------------------------------------- main


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ZenTray 文本工具箱 service 插件")
    sub = p.add_subparsers(dest="action")
    for name in ("start", "serve"):
        sp = sub.add_parser(name)
        sp.add_argument("--port", type=int, default=_default_port())
        sp.add_argument("--no-open", action="store_true",
                        help="抑制自动打开浏览器（selftest 用）")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = p.parse_args(argv)

    return {
        "start": cmd_start,
        "serve": cmd_serve,
        "stop": cmd_stop,
        "status": cmd_status,
        "selftest": cmd_selftest,
    }.get(args.action, cmd_status)(args)


if __name__ == "__main__":
    raise SystemExit(main())
