"""插件报告通知：模板渲染纯函数 + 插件级渠道/通知格式设置解析。"""
from __future__ import annotations

import json

from zentray.services.notification import render_template


def test_render_template_substitution():
    ctx = {"name": "ai-news-digest", "status": "执行成功", "summary": "12 条", "result": "日报已生成"}
    assert render_template("脚本: {name}", ctx) == "脚本: ai-news-digest"
    assert render_template("{status}\n{result}", ctx) == "执行成功\n日报已生成"


def test_render_template_unknown_placeholder_kept():
    # 用户手误的占位符原样保留，不抛异常
    assert render_template("{nope} {name}", {"name": "x"}) == "{nope} x"
    assert render_template("", {"name": "x"}) == ""


def test_plugin_notify_settings_parse(tmp_path, monkeypatch):
    from zentray.services import settings_manager as sm

    f = tmp_path / "settings.json"
    monkeypatch.setattr(sm, "SETTINGS_FILE", f)
    sm.SettingsManager.reload()  # 无文件 → 默认值
    mgr = sm.SettingsManager()
    assert mgr.notification.plugin_title_template == "脚本: {name}"
    assert mgr.notification.plugin_body_template == "{result}"
    assert mgr.ops.plugin_notify_channels == {}

    f.write_text(
        json.dumps(
            {
                "notification": {
                    "plugin_title_template": "📦 {name}",
                    "plugin_body_template": "{status}|{result}",
                },
                "ops": {
                    "plugin_notify_channels": {
                        "email-digest": ["app_popup", "feishu_bot", "bogus"],
                        "text-toolbox": "notalist",
                    },
                    "notify_channels": ["wxpusher"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sm.SettingsManager.reload()
    mgr = sm.SettingsManager()
    assert mgr.notification.plugin_title_template == "📦 {name}"
    assert mgr.notification.plugin_body_template == "{status}|{result}"
    # 渠道白名单清洗；非列表值整键丢弃
    assert mgr.ops.plugin_notify_channels == {"email-digest": ["app_popup", "feishu_bot"]}
    # 旧全局键保留，作未配置插件的回退
    assert mgr.ops.notify_channels == ["wxpusher"]
