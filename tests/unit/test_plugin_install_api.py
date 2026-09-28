"""插件预览校验 / 路径安全 / zip 安装 / 运行历史端点。"""
import json
import zipfile
from pathlib import Path

from zentray.api.handlers import (
    _plugin_run_log,
    _plugin_runs,
    _safe_plugin_path,
    _validate_plugin_path,
    _install_plugin_zip,
)

ROOT = Path(__file__).resolve().parents[2]


def test_validate_bundled_net_cleanup():
    path = ROOT / "bundled_plugins" / "net-cleanup"
    code, body = _validate_plugin_path({"path": str(path)})
    assert code == 200
    assert body["ok"] is True
    assert body["preview"]["id"] == "net-cleanup"


def test_reject_outside_home(tmp_path, monkeypatch):
    # /etc 通常不在允许范围
    path, err = _safe_plugin_path("/etc")
    assert path is None
    assert err and "允许范围" in err


def _make_plugin_dir(root: Path, pid: str = "zip-plug") -> Path:
    d = root / pid
    d.mkdir(parents=True)
    (d / "plugin.yaml").write_text(
        f"""id: {pid}
name: zip插件
version: 0.1.0
type: script
api_version: 1
entry: run.sh
""",
        encoding="utf-8",
    )
    run = d / "run.sh"
    run.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    run.chmod(0o755)
    return d


def test_install_zip_flat(tmp_data_dir):
    """根目录含 plugin.yaml 的 zip 正常安装。"""
    # zip 必须放在允许根内（DATA_DIR 已被 conftest 指到 tmp）
    src_root = tmp_data_dir / "zipsrc"
    plug = _make_plugin_dir(src_root)
    zp = src_root / "plug.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for f in plug.rglob("*"):
            zf.write(f, f.relative_to(plug))

    user_dir = tmp_data_dir / "plugins"
    code, body = _install_plugin_zip({"path": str(zp)})
    assert code == 200, body
    assert body["ok"] is True
    assert (user_dir / "zip-plug" / "run.sh").is_file()


def test_install_zip_single_subdir(tmp_data_dir):
    """唯一一级子目录含 plugin.yaml 的 zip 正常安装。"""
    src_root = tmp_data_dir / "zipsrc2"
    plug = _make_plugin_dir(src_root / "inner")
    zp = src_root / "plug.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for f in plug.rglob("*"):
            # 布局形如 `zip -r plug.zip zip-plug/`：zip-plug/plugin.yaml 一层
            zf.write(f, f.relative_to(plug.parent))

    user_dir = tmp_data_dir / "plugins"
    code, body = _install_plugin_zip({"path": str(zp)})
    assert code == 200, body
    assert (user_dir / "zip-plug" / "run.sh").is_file()


def test_install_zip_slip_rejected(tmp_data_dir):
    """zip-slip：../ 逃逸成员必须被拒绝且不落地任何文件。"""
    src_root = tmp_data_dir / "zipsrc3"
    src_root.mkdir()
    zp = src_root / "evil.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("plugin.yaml", "id: evil\nname: e\n")
        zf.writestr("../evil.sh", "#!/bin/sh\n")

    code, body = _install_plugin_zip({"path": str(zp)})
    assert code == 400
    assert "非法" in body["error"]
    assert not (src_root / "evil.sh").exists()


def test_install_zip_no_manifest(tmp_data_dir):
    src_root = tmp_data_dir / "zipsrc4"
    src_root.mkdir()
    zp = src_root / "plain.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("readme.txt", "not a plugin")

    code, body = _install_plugin_zip({"path": str(zp)})
    assert code == 400
    assert "plugin.yaml" in body["error"]


def test_install_zip_absolute_member_rejected(tmp_data_dir):
    src_root = tmp_data_dir / "zipsrc5"
    src_root.mkdir()
    zp = src_root / "abs.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("/etc/evil.conf", "x")

    code, body = _install_plugin_zip({"path": str(zp)})
    assert code == 400


def _write_runs(runs_dir: Path, entries: list):
    runs_dir.mkdir(parents=True, exist_ok=True)
    for i, e in enumerate(entries):
        (runs_dir / f"2026092{8 - i}_12000{i}_plug.json").write_text(
            json.dumps(e, ensure_ascii=False), encoding="utf-8"
        )


def test_plugin_runs_listing(tmp_data_dir):
    runs_dir = tmp_data_dir / "ops_runs"
    _write_runs(
        runs_dir,
        [
            {"id": "plug", "ok": True, "summary": "a"},
            {"id": "plug", "ok": False, "summary": "b"},
        ],
    )
    # last.json 应被排除
    (runs_dir / "last.json").write_text(
        json.dumps({"id": "plug", "ok": True}), encoding="utf-8"
    )
    code, body = _plugin_runs({})
    assert code == 200
    assert body["count"] == 2
    assert body["items"][0]["summary"] == "a"  # 时间戳倒序


def test_plugin_runs_limit(tmp_data_dir, monkeypatch):
    runs_dir = tmp_data_dir / "ops_runs"
    _write_runs(runs_dir, [{"id": f"p{i}", "ok": True} for i in range(5)])
    code, body = _plugin_runs({"limit": "2"})
    assert code == 200
    assert body["count"] == 2


def test_plugin_run_log_path_traversal(tmp_data_dir):
    # 无分隔符但文件不存在
    code, body = _plugin_run_log({"file": "nope.log"})
    assert code == 404
    # 路径分隔符拒绝
    code, body = _plugin_run_log({"file": "../settings.json"})
    assert code == 400
    code, body = _plugin_run_log({"file": "sub/dir/x.log"})
    assert code == 400


def test_plugin_run_log_reads_content(tmp_data_dir):
    runs_dir = tmp_data_dir / "ops_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "20260928_120000_plug.log").write_text(
        "$ run.sh\nhello\n", encoding="utf-8"
    )
    code, body = _plugin_run_log({"file": "20260928_120000_plug.log"})
    assert code == 200
    assert "hello" in body["content"]
    assert body["truncated"] is False


# ==========================================
# v2.1：installed_at / 列表元数据
# ==========================================


def _zip_plugin(src_root: Path, pid: str = "zip-plug") -> Path:
    plug = _make_plugin_dir(src_root, pid)
    zp = src_root / "plug.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for f in plug.rglob("*"):
            zf.write(f, f.relative_to(plug))
    return zp


def test_install_writes_installed_at(tmp_data_dir):
    zp = _zip_plugin(tmp_data_dir / "zipsrc6")
    code, body = _install_plugin_zip({"path": str(zp)})
    assert code == 200, body
    from zentray.services.settings_manager import SettingsManager

    assert "zip-plug" in SettingsManager.reload().ops.installed_at


def test_plugins_list_v21_metadata(tmp_data_dir, monkeypatch):
    from zentray.api.handlers import _plugins_list
    from zentray.plugins import triggers as _triggers

    monkeypatch.setattr(_triggers, "STATE_FILE", tmp_data_dir / "pt.json")
    body = _plugins_list(scan_always=True)
    items = {i["id"]: i for i in body["items"]}
    nc = items["net-cleanup"]
    # 新字段齐备
    assert nc["category"] == ""  # category 标签阶段 5 才补
    assert nc["params"] == []
    assert nc["updated_at"]  # mtime 兜底
    assert nc["trigger_override"] is False
    assert isinstance(nc["triggers"], list)

    # 覆盖层生效：triggers 展示 effective，trigger_override 置位
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.trigger_overrides = {"net-cleanup": [{"type": "interval", "minutes": 15}]}
    body = _plugins_list(scan_always=True)
    nc = {i["id"]: i for i in body["items"]}["net-cleanup"]
    assert nc["triggers"] == ["每 15 分钟"]
    assert nc["trigger_override"] is True


def test_preview_zip_validates_without_installing(tmp_data_dir):
    zp = _zip_plugin(tmp_data_dir / "zipsrc7")
    from zentray.api.handlers import _preview_plugin_zip

    code, body = _preview_plugin_zip({"path": str(zp)})
    assert code == 200
    assert body["ok"] is True
    assert body["preview"]["id"] == "zip-plug"
    # 预览不落地：用户目录无插件，临时目录已清理
    user_dir = tmp_data_dir / "plugins"
    assert not (user_dir / "zip-plug").exists()
    assert not list((tmp_data_dir / "tmp").glob("plugin_install_*"))


def test_preview_zip_invalid_manifest(tmp_data_dir):
    src_root = tmp_data_dir / "zipsrc8"
    src_root.mkdir()
    zp = src_root / "bad.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("plugin.yaml", "id: bad\nname: 缺字段\n")
    from zentray.api.handlers import _preview_plugin_zip

    code, body = _preview_plugin_zip({"path": str(zp)})
    assert code == 200
    assert body["ok"] is False
    assert body["errors"]
