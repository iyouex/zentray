# tests/unit/test_ai_assist.py
"""AI 场景能力：fake 模式三方法、JSON 围栏剥离、草稿归一化、路由门控。"""
import pytest

from zentray.services.ai_assist import (
    AIAssistError,
    AIAssistService,
    _clean_draft,
    _clean_suggestions,
    _strip_fences,
)


# ---- 纯函数 ----

def test_strip_fences_variants():
    assert _strip_fences('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_fences('前置说明 {"a":1} 后置') == '{"a":1}'
    assert _strip_fences('[1,2]') == '[1,2]'
    assert _strip_fences("") == ""


def test_clean_draft_normalizes():
    d = _clean_draft(
        {
            "title": "  x  ",
            "priority": "URGENT",
            "deadline": "2026-9-5",
            "reminder_time": "9:05",
            "subtasks": "甲\n乙；丙",
        }
    )
    assert d["title"] == "x"
    assert d["priority"] == "medium"  # 非法回退
    assert d["deadline"] == "2026-09-05"
    assert d["reminder_time"] == "09:05"
    assert d["subtasks"] == ["甲", "乙", "丙"]


def test_clean_suggestions_filters_and_caps():
    out = _clean_suggestions(
        [
            {"type": "hack", "text": "x"},  # 非法类型 → review
            {"type": "priority", "text": "提级", "patch": {"priority": "high"}},
            {"type": "deadline", "text": "无补丁日期", "patch": {"deadline": "不合法"}},
            {"text": ""},  # 空 text 丢弃
        ]
    )
    # 非法 patch 的 deadline 建议保留为纯文本（patch 置空，前端不可应用）
    assert [s["type"] for s in out] == ["review", "priority", "deadline"]
    assert out[1]["patch"] == {"priority": "high"}
    assert out[2]["patch"] == {}


# ---- fake 模式服务 ----

@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("ZENTRAY_AI_FAKE", "1")
    return AIAssistService


TODAY = "2026-09-24"


def test_parse_text_fake(fake_ai):
    d = fake_ai.parse_text("发布季度版本", ["工作", "个人"], TODAY)
    assert d["title"]
    assert d["priority"] in ("high", "medium", "low")
    assert d["subtasks"]


def test_parse_text_empty_raises(fake_ai):
    with pytest.raises(AIAssistError):
        fake_ai.parse_text("  ", [], TODAY)


def test_parse_image_fake(fake_ai):
    drafts = fake_ai.parse_image("data:image/png;base64,AAAA", ["工作"], TODAY)
    assert len(drafts) == 1 and drafts[0]["title"]


def test_parse_image_bad_input(fake_ai):
    with pytest.raises(AIAssistError):
        fake_ai.parse_image("not-a-data-url", [], TODAY)


def test_suggest_fake(fake_ai):
    out = fake_ai.suggest(
        [{"title": "甲", "category": "工作", "priority": "low", "deadline": "2026-09-01",
          "subtask_done": 0, "subtask_total": 0}],
        TODAY,
    )
    assert out and any(s["type"] == "priority" for s in out)  # 过期任务给提级建议


def test_suggest_empty_raises(fake_ai):
    with pytest.raises(AIAssistError):
        fake_ai.suggest([], TODAY)


# ---- 路由门控（借 handlers 上下文）----

@pytest.fixture
def api(task_service, tmp_data_dir):
    from zentray.api.handlers import ApiContext, set_api_context

    set_api_context(ApiContext(task_service=task_service))
    return task_service


def _set_features(**kw):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    sm.ai.features.smart_parse = kw.get("smart_parse", False)
    sm.ai.features.image_ocr = kw.get("image_ocr", False)
    sm.ai.features.task_suggest = kw.get("task_suggest", False)
    return sm


def test_routes_403_when_disabled(api):
    from zentray.api.handlers import handle_request

    assert handle_request("POST", "/api/ai/parse", {"text": "x"})[0] == 403
    assert handle_request("POST", "/api/ai/ocr", {"image": "data:image/png;base64,AA"})[0] == 403
    assert handle_request("POST", "/api/ai/suggest", {})[0] == 403


def test_routes_happy_path_fake(api, monkeypatch):
    from zentray.api.handlers import handle_request

    monkeypatch.setenv("ZENTRAY_AI_FAKE", "1")
    _set_features(smart_parse=True, image_ocr=True, task_suggest=True)
    api.create_task({"title": "过期任务", "category": "工作", "deadline": "2026-01-01"})

    code, body = handle_request("POST", "/api/ai/parse", {"text": "写周报"})
    assert code == 200 and body["draft"]["title"]

    code, body = handle_request("POST", "/api/ai/ocr", {"image": "data:image/png;base64,AA=="})
    assert code == 200 and len(body["drafts"]) >= 1

    code, body = handle_request("POST", "/api/ai/suggest", {})
    assert code == 200 and body["suggestions"]


def test_suggest_with_dict_subtasks(api, monkeypatch):
    """回归：真机数据里子任务是 dict（曾用 s.status 属性访问炸 500）。"""
    from zentray.api.handlers import handle_request

    monkeypatch.setenv("ZENTRAY_AI_FAKE", "1")
    _set_features(task_suggest=True)
    api.create_task(
        {"title": "带子任务的任务", "category": "工作",
         "subtasks": [{"title": "甲", "status": "done"}, {"title": "乙", "status": "active"}]}
    )
    code, body = handle_request("POST", "/api/ai/suggest", {})
    assert code == 200 and body["suggestions"]


def test_routes_400_missing_params(api):
    from zentray.api.handlers import handle_request

    _set_features(smart_parse=True, image_ocr=True)
    assert handle_request("POST", "/api/ai/parse", {})[0] == 400
    assert handle_request("POST", "/api/ai/ocr", {})[0] == 400


def test_settings_features_roundtrip(tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    sm.ai.features.smart_parse = True
    sm.ai.features.image_ocr = True
    sm.save()
    SettingsManager._instance = None  # 重读
    again = SettingsManager().ai.features
    assert again.smart_parse and again.image_ocr and not again.task_suggest
