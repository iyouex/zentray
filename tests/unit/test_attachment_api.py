# tests/unit/test_attachment_api.py
"""任务附件/链接 API——URL 走浏览器、本地路径走系统应用、缩略图仅放行图片后缀。"""
import base64

import pytest

from zentray.api.handlers import (
    ApiContext,
    handle_request,
    serve_attachment_thumb,
    set_api_context,
)

# 1x1 红 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def api(task_service):
    set_api_context(ApiContext(task_service=task_service))
    return task_service


def test_open_link_uses_browser(api, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda u: opened.append(u) or True)
    code, body = handle_request(
        "POST", "/api/attachments/open", {"value": "https://example.com/x"}
    )
    assert code == 200
    assert opened == ["https://example.com/x"]


def test_open_file_delegates_system(api, monkeypatch, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("x", encoding="utf-8")
    calls = []
    monkeypatch.setattr("zentray.api.handlers._open_with_system", lambda p: calls.append(p))
    code, body = handle_request("POST", "/api/attachments/open", {"value": str(f)})
    assert code == 200
    assert calls == [f]


def test_open_missing_file_404(api):
    code, body = handle_request("POST", "/api/attachments/open", {"value": "/no/such/a.png"})
    assert code == 404


def test_open_empty_value_400(api):
    code, _ = handle_request("POST", "/api/attachments/open", {"value": "  "})
    assert code == 400


def test_thumb_serves_png(api, tmp_path):
    f = tmp_path / "pic.png"
    f.write_bytes(_PNG)
    code, ctype, blob = serve_attachment_thumb({"path": str(f)})
    assert code == 200
    assert ctype == "image/png"
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumb_rejects_non_image(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    code, _, _ = serve_attachment_thumb({"path": str(f)})
    assert code == 404


def test_thumb_missing_file_404(tmp_path):
    code, _, _ = serve_attachment_thumb({"path": str(tmp_path / "none.png")})
    assert code == 404
