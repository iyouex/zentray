"""plugin.yaml 校验测试。"""
from pathlib import Path

import pytest

from zentray.plugins.manifest import validate_plugin_dir
from zentray.plugins.models import PluginType

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plugins"


def test_sample_script_valid():
    r = validate_plugin_dir(FIXTURES / "sample-script")
    assert r.ok, r.error_text()
    assert r.manifest is not None
    assert r.manifest.id == "sample-script"
    assert r.manifest.type == PluginType.SCRIPT
    assert r.manifest.entry_path.is_file()


def test_sample_service_valid():
    r = validate_plugin_dir(FIXTURES / "sample-service")
    assert r.ok, r.error_text()
    assert r.manifest.type == PluginType.SERVICE


def test_bad_escape_rejected():
    r = validate_plugin_dir(FIXTURES / "bad-escape")
    assert not r.ok
    assert any(".." in e or "相对" in e or "越出" in e for e in r.errors)


def test_missing_dir():
    r = validate_plugin_dir(FIXTURES / "no-such-plugin")
    assert not r.ok
