# zentray/api/server.py
"""
本机环回 HTTP 服务（stdlib），给 Vue 静态页 + REST API 使用。
"""
from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from zentray.api.handlers import handle_request, serve_attachment_thumb
from zentray.resources import get_resource_path

logger = logging.getLogger(__name__)

_server_instance: Optional["LocalApiServer"] = None


def web_dist_dir() -> Path:
    """打包/开发下的 Vue dist 目录。"""
    candidates = [
        get_resource_path("web/dist"),
        Path(__file__).resolve().parents[2] / "web" / "dist",
        Path(__file__).resolve().parents[2] / "zentray" / "web_dist",
    ]
    for p in candidates:
        if p.is_dir() and (p / "index.html").exists():
            return p
    return candidates[1]


def vue_ui_available() -> bool:
    d = web_dist_dir()
    return d.is_dir() and (d / "index.html").exists()


class _Handler(BaseHTTPRequestHandler):
    dist_dir: Path = Path(".")

    def log_message(self, fmt, *args):
        logger.debug("API %s - %s", self.address_string(), fmt % args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return None
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = {k: (v[0] if v else "") for k, v in parse_qs(parsed.query).items()}

        if path.startswith("/api/"):
            # 附件缩略图：二进制响应，走单独分支（其余 API 一律 JSON）
            if method == "GET" and path == "/api/attachments/thumb":
                code, ctype, blob = serve_attachment_thumb(qs)
                self.send_response(code)
                self._cors()
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            body = self._read_body() if method in ("POST", "PUT") else None
            code, data = handle_request(method, path, body, query=qs)
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 静态资源（Vue dist）
        self._serve_static(path)

    def _serve_static(self, path: str):
        dist = self.dist_dir
        if path in ("", "/"):
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        # SPA fallback
        file_path = (dist / rel).resolve()
        try:
            file_path.relative_to(dist.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not file_path.is_file():
            file_path = dist / "index.html"
        if not file_path.is_file():
            self.send_error(404, "Vue dist not found. Run: npm run build in web/")
            return
        data = file_path.read_bytes()
        ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class LocalApiServer:
    """127.0.0.1 上的轻量服务。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.base_url = ""

    def start(self) -> str:
        if self._httpd:
            return self.base_url
        dist = web_dist_dir()
        handler = type("H", (_Handler,), {"dist_dir": dist})
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        actual_port = self._httpd.server_address[1]
        self.port = actual_port
        self.base_url = f"http://{self.host}:{actual_port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Local API + Vue static: %s (dist=%s)", self.base_url, dist)
        return self.base_url

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None


def get_api_server() -> LocalApiServer:
    global _server_instance
    if _server_instance is None:
        _server_instance = LocalApiServer()
    return _server_instance
