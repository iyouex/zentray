"""发布清单脚本：生成规则、复核，以及与客户端的契约（脚本产出的清单客户端必须认）。"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from zentray.services import updater

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compose_update_manifest.py"
TAG = "v9.9.9"
VERSION = "9.9.9"


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("compose_update_manifest", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digests(script, size=120 * 1024 * 1024):
    return {key: {"size": size + i, "sha256": f"{i:064x}"}
            for i, key in enumerate(script.PLATFORMS)}


def _composed(script, **overrides):
    args = dict(tag=TAG, notes="## 主题\n- 甲", published_at="2026-11-23T12:00:00Z",
                digests=_digests(script))
    args.update(overrides)
    return script.compose_manifest(**args)


# —— 平台表与生成规则 ————————————————————————————————————————————————————————————


def test_platform_table_matches_the_client(script):
    """脚本不 import zentray，平台表是手抄的——两处一旦漂移，这里先红。"""
    assert script.PLATFORMS == {key: suffix for key, suffix in updater.PLATFORMS.values()}


def test_compose_is_complete_and_deterministic(script):
    manifest = _composed(script)
    assert list(manifest) == ["version", "pub_date", "notes", "platforms"]
    assert manifest["version"] == VERSION and manifest["notes"] == "## 主题\n- 甲"
    assert list(manifest["platforms"]) == list(script.PLATFORMS)
    linux = manifest["platforms"]["linux-amd64"]
    assert linux == {
        "url": f"https://github.com/iyouex/zentray/releases/download/{TAG}/zentray_{VERSION}_amd64.deb",
        "size": 120 * 1024 * 1024, "sha256": "0" * 64}
    assert script.validate_manifest(manifest) == []


def test_compose_rejects_incomplete_or_invalid_inputs(script):
    with pytest.raises(script.ManifestError, match="非法 tag"):
        _composed(script, tag="0.9.9")
    with pytest.raises(script.ManifestError, match="非法 tag"):
        _composed(script, tag="v0.8.0-rc1")  # 预发布不进「最新」清单
    digests = _digests(script)
    del digests["macos-arm64"]
    with pytest.raises(script.ManifestError, match="缺少平台安装包.*macos-arm64"):
        _composed(script, digests=digests)
    digests = _digests(script)
    digests["windows-x64"]["sha256"] = "abc"
    with pytest.raises(script.ManifestError, match="windows-x64 的大小或哈希不合法"):
        _composed(script, digests=digests)


def test_notes_are_capped(script):
    manifest = _composed(script, notes="很长" * 5000)
    assert len(manifest["notes"]) == script.NOTES_LIMIT


# —— 复核 ———————————————————————————————————————————————————————————————————————————


def _break(manifest, key, field, value):
    manifest["platforms"][key][field] = value
    return manifest


@pytest.mark.parametrize("mutate, expected", [
    (lambda m: m["platforms"].pop("windows-x64"), "缺少 windows-x64"),
    (lambda m: _break(m, "linux-amd64", "url", "https://evil.example/x.deb"), "linux-amd64 的下载地址"),
    (lambda m: _break(m, "linux-amd64", "url",
                      f"https://github.com/iyouex/zentray/releases/download/v9.9.8/zentray_9.9.8_amd64.deb"),
     "linux-amd64 的下载地址"),
    (lambda m: _break(m, "macos-arm64", "sha256", "zz"), "macos-arm64 的 sha256"),
    (lambda m: _break(m, "macos-arm64", "size", 0), "macos-arm64 的大小"),
    (lambda m: m.update(version="x"), "版本号不合法"),
])
def test_validate_catches_tampering(script, mutate, expected):
    manifest = _composed(script)
    mutate(manifest)
    problems = script.validate_manifest(manifest)
    assert problems and expected in problems[0], problems


def test_validate_rejects_non_objects(script):
    assert script.validate_manifest(None) == ["清单不是 JSON 对象"]


# —— 与客户端的契约 ————————————————————————————————————————————————————————————————


def test_client_accepts_what_the_script_produces(script):
    manifest = _composed(script)
    for _system, (key, suffix) in updater.PLATFORMS.items():
        result = updater.manifest_result(manifest, key, suffix)
        assert result["has_update"] and result["asset_ready"], key
        assert result["version"] == VERSION
        assert result["asset_url"] == manifest["platforms"][key]["url"]
        assert result["asset_size"] == manifest["platforms"][key]["size"]
        assert result["sha256"] == manifest["platforms"][key]["sha256"]


def test_client_refuses_a_tampered_entry_instead_of_downloading_elsewhere(script):
    manifest = _composed(script)
    manifest["platforms"]["linux-amd64"]["url"] = "https://evil.example/zentray_9.9.9_amd64.deb"
    key, suffix = updater.PLATFORMS["linux"]
    result = updater.manifest_result(manifest, key, suffix)
    assert result["has_update"] and not result["asset_ready"]
    assert result["asset_url"] == ""


# —— 对接 Release：缺包、大小、deb 内嵌版本 ——————————————————————————————————————————


def _release(script, names=None):
    names = names if names is not None else list(script.asset_names(VERSION).values())
    return {"assets": [{"name": n, "size": None} for n in names], "body": "## 主题",
            "publishedAt": "2026-11-23T12:00:00Z", "isDraft": False}


@pytest.fixture
def fake_gh(script, monkeypatch, tmp_path):
    """gh 假实现：下载 = 往目标目录写一个内容确定的文件。"""
    uploaded = []

    def gh(*args):
        if args[:2] == ("release", "download"):
            name = args[args.index("--pattern") + 1]
            target = Path(args[args.index("--dir") + 1]) / name
            target.write_bytes(b"payload:" + name.encode())
            return ""
        if args[:2] == ("release", "upload"):
            uploaded.append(args)
            return ""
        raise AssertionError(f"unexpected gh call: {args}")

    monkeypatch.setattr(script, "gh", gh)
    monkeypatch.setattr(script, "deb_version", lambda path: VERSION)
    return uploaded


def test_build_refuses_when_a_platform_asset_is_missing(script, fake_gh, monkeypatch, tmp_path):
    names = list(script.asset_names(VERSION).values())
    monkeypatch.setattr(script, "gh_json", lambda *a: _release(script, names[:2]))
    with pytest.raises(script.ManifestError, match="缺少 zentray_9.9.9_macos_arm64.zip"):
        script.build(TAG, tmp_path)
    assert fake_gh == []


def test_build_digests_every_asset_and_passes_review(script, fake_gh, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "gh_json", lambda *a: _release(script))
    manifest, log = script.build(TAG, tmp_path)

    assert script.validate_manifest(manifest) == []
    for key, name in script.asset_names(VERSION).items():
        payload = b"payload:" + name.encode()
        assert manifest["platforms"][key]["size"] == len(payload)
        assert manifest["platforms"][key]["sha256"] == script.sha256_file(tmp_path / name)
    assert manifest["notes"] == "## 主题" and manifest["pub_date"] == "2026-11-23T12:00:00Z"
    assert len(log) == 3


def test_build_refuses_a_deb_from_an_unbumped_branch_build(script, fake_gh, monkeypatch, tmp_path):
    """v0.7.23 的 Windows 资产曾被未升版本号的分支构建覆盖——同类事故在清单这一步就要被拦下。"""
    monkeypatch.setattr(script, "gh_json", lambda *a: _release(script))
    monkeypatch.setattr(script, "deb_version", lambda path: "9.9.9+staging.4")
    with pytest.raises(script.ManifestError, match="Debian 版本是 9.9.9\\+staging.4"):
        script.build(TAG, tmp_path)


def test_build_flags_a_draft_but_proceeds(script, fake_gh, monkeypatch, tmp_path):
    release = {**_release(script), "isDraft": True}
    monkeypatch.setattr(script, "gh_json", lambda *a: release)
    manifest, log = script.build(TAG, tmp_path)
    assert any("草稿" in line for line in log)
    assert script.validate_manifest(manifest) == []


def test_deb_version_needs_dpkg_deb(script, monkeypatch):
    monkeypatch.setattr(script.shutil, "which", lambda name: None)
    assert script.deb_version(Path("x.deb")) is None
    monkeypatch.setattr(script.shutil, "which", lambda name: "/usr/bin/dpkg-deb")
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="9.9.9\n"))
    assert script.deb_version(Path("x.deb")) == "9.9.9"


# —— 命令行：默认只读，--upload 才动 Release ———————————————————————————————————————————


def _fake_build(script, monkeypatch):
    manifest = _composed(script)
    monkeypatch.setattr(script, "build", lambda tag, workdir: (manifest, ["核对记录"]))


def test_cli_prints_without_touching_the_release(script, monkeypatch, capsys):
    _fake_build(script, monkeypatch)
    assert script.main([TAG]) == 0
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):])["version"] == VERSION
    assert "核对记录" in out


def test_cli_writes_the_file_when_asked(script, monkeypatch, tmp_path, capsys):
    _fake_build(script, monkeypatch)
    target = tmp_path / "latest.json"
    assert script.main([TAG, "--output", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == VERSION
    assert "✓ 清单已写入" in capsys.readouterr().out


def test_cli_uploads_the_manifest_as_the_last_step(script, fake_gh, monkeypatch, capsys):
    _fake_build(script, monkeypatch)
    assert script.main([TAG, "--upload"]) == 0
    assert len(fake_gh) == 1 and fake_gh[0][:3] == ("release", "upload", TAG)
    assert fake_gh[0][3].endswith("latest.json") and "--clobber" in fake_gh[0]
    assert "已上传" in capsys.readouterr().out


def test_cli_failure_never_uploads(script, monkeypatch, capsys):
    def explode(tag, workdir):
        raise script.ManifestError("缺少平台安装包：macos-arm64")

    monkeypatch.setattr(script, "build", explode)
    monkeypatch.setattr(script, "gh", lambda *a: pytest.fail("失败路径不得调用 gh"))
    assert script.main([TAG, "--upload"]) == 1
    assert "macos-arm64" in capsys.readouterr().err


def test_cli_rejects_output_and_upload_together(script):
    with pytest.raises(SystemExit):
        script.main([TAG, "--upload", "--output", "x.json"])
