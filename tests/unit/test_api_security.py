# tests/unit/test_api_security.py
"""D5 本机 API 鉴权：Host 防 DNS rebinding + 写请求 Origin 防跨域写 + CORS 收紧。"""
import json
import urllib.error
import urllib.request

import pytest

from zentray.api.server import (
    LocalApiServer,
    host_header_allowed,
    origin_header_allowed,
)


class TestHostHeaderAllowed:
    def test_loopback_names_with_or_without_port(self):
        assert host_header_allowed("127.0.0.1")
        assert host_header_allowed("127.0.0.1:39571")
        assert host_header_allowed("localhost:8080")
        assert host_header_allowed("LOCALHOST")

    def test_ipv6_loopback_bracket_form(self):
        assert host_header_allowed("[::1]:9000")

    def test_foreign_host_rejected(self):
        assert not host_header_allowed("evil.com")
        assert not host_header_allowed("evil.com:8080")
        assert not host_header_allowed("zentray.example")

    def test_empty_rejected(self):
        assert not host_header_allowed("")
        assert not host_header_allowed(None)


class TestOriginHeaderAllowed:
    def test_absent_origin_passes(self):
        # 同源 GET / 本地 curl / Qt 请求不带 Origin
        assert origin_header_allowed("", 1234)
        assert origin_header_allowed(None, 1234)

    def test_own_origin_passes(self):
        assert origin_header_allowed("http://127.0.0.1:1234", 1234)
        assert origin_header_allowed("http://localhost:1234/", 1234)

    def test_foreign_origin_rejected(self):
        assert not origin_header_allowed("http://evil.com", 1234)
        assert not origin_header_allowed("https://evil.com", 1234)
        assert not origin_header_allowed("null", 1234)

    def test_wrong_port_rejected(self):
        # 他端口可能是本机其它服务，其页面不得写我们
        assert not origin_header_allowed("http://127.0.0.1:9999", 1234)


@pytest.fixture
def server(tmp_data_dir):
    srv = LocalApiServer()
    url = srv.start()
    yield srv, url
    srv.stop()


def _http(url, path, method="GET", headers=None, body=None):
    req = urllib.request.Request(
        url + path,
        data=body,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class TestHttpGuard:
    def test_same_origin_health_ok(self, server):
        _, url = server
        code, _body = _http(url, "/api/health")
        assert code == 200

    def test_foreign_host_403(self, server):
        _, url = server
        code, _body = _http(url, "/api/health", headers={"Host": "evil.com"})
        assert code == 403

    def test_cross_origin_write_403(self, server):
        _, url = server
        code, _body = _http(
            url,
            "/api/attachments/open",
            method="POST",
            headers={"Origin": "http://evil.com", "Content-Type": "application/json"},
            body=json.dumps({}).encode(),
        )
        assert code == 403

    def test_own_origin_write_passes_guard(self, server):
        srv, url = server
        origin = f"http://127.0.0.1:{srv.port}"
        code, body = _http(
            url,
            "/api/attachments/open",
            method="POST",
            headers={"Origin": origin, "Content-Type": "application/json"},
            body=json.dumps({}).encode(),
        )
        # 防线放行（非 403），进入业务层（空 body 的业务结果任意）
        assert code != 403
        assert json.loads(body).get("error") or code in (200, 400)

    def test_no_cors_header_for_cross_origin(self, server):
        _, url = server
        req = urllib.request.Request(url + "/api/health", headers={"Origin": "http://evil.com"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") is None

    def test_cors_echoed_for_own_origin(self, server):
        srv, url = server
        origin = f"http://127.0.0.1:{srv.port}"
        req = urllib.request.Request(url + "/api/health", headers={"Origin": origin})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") == origin
