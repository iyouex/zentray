"""跨设备迁移：导出 / 导入替换 round-trip。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from zentray.services import data_migration as mig


def _seed(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "active_tasks.json").write_text(
        json.dumps([{"id": "t1", "title": "hello"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "periodic_templates.json").write_text("[]", encoding="utf-8")
    (data_dir / "settings.json").write_text(
        json.dumps({"appearance": {"theme": "dark", "autostart": False}}),
        encoding="utf-8",
    )
    (data_dir / "activity.jsonl").write_text(
        '{"time":"2026-01-01T00:00:00","category":"task","action":"create"}\n',
        encoding="utf-8",
    )
    arch = data_dir / "archive"
    arch.mkdir()
    (arch / "2026-01-01.log").write_text("done\n", encoding="utf-8")
    rev = data_dir / "reviews"
    rev.mkdir()
    (rev / "2026-01-01.md").write_text("# review\n", encoding="utf-8")
    (data_dir / ".env").write_text("AI_API_KEY=secret\n", encoding="utf-8")


def test_export_default_excludes_env(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    result = mig.create_export_zip(data_dir=root)
    assert result.ok, result.message
    assert result.path
    with zipfile.ZipFile(result.path) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "active_tasks.json" in names
        assert ".env" not in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == "zentray-backup"
        assert "env" not in manifest["include"]


def test_export_can_include_env(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    result = mig.create_export_zip(["tasks", "env"], data_dir=root)
    assert result.ok
    with zipfile.ZipFile(result.path) as zf:
        assert ".env" in zf.namelist()


def test_import_replace_roundtrip(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _seed(src)
    _seed(dst)
    # 修改目标，导入后应被覆盖
    (dst / "active_tasks.json").write_text(
        json.dumps([{"id": "old", "title": "old"}], ensure_ascii=False),
        encoding="utf-8",
    )

    exported = mig.create_export_zip(
        ["tasks", "settings", "archive"],
        data_dir=src,
    )
    assert exported.ok

    imported = mig.import_replace(
        exported.path,
        ["tasks", "settings", "archive"],
        data_dir=dst,
        make_safety_backup=True,
    )
    assert imported.ok, imported.message
    assert imported.safety_backup
    tasks = json.loads((dst / "active_tasks.json").read_text(encoding="utf-8"))
    assert tasks[0]["id"] == "t1"
    settings = json.loads((dst / "settings.json").read_text(encoding="utf-8"))
    assert settings["appearance"]["theme"] == "dark"
    assert (dst / "archive" / "2026-01-01.log").read_text(encoding="utf-8") == "done\n"


def test_pack_archive(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    result = mig.pack_archive(data_dir=root)
    assert result.ok
    with zipfile.ZipFile(result.path) as zf:
        assert any(n.startswith("archive/") for n in zf.namelist())


def test_list_include_options():
    opts = mig.list_include_options()
    keys = {o["key"] for o in opts}
    assert "tasks" in keys and "env" in keys
    env = next(o for o in opts if o["key"] == "env")
    assert env["sensitive"] is True
    assert env["default"] is False


# —— 选择性恢复：include 子键 + 分区替换 + 预览 ——


def _seed_rich(data_dir: Path) -> None:
    """分区测试数据：一次性/周期任务、多节设置、plan/review 复盘、跨月归档、双插件。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "active_tasks.json").write_text(
        json.dumps(
            [
                {"id": "a1", "title": "一次性-备份", "task_type": "one-time"},
                {"id": "a2", "title": "一次性-备份2", "task_type": "one-time"},
                {
                    "id": "p1",
                    "title": "周期-备份",
                    "task_type": "periodic_instance",
                    "template_id": "tpl-x",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "periodic_templates.json").write_text(
        json.dumps([{"id": "tpl-x", "title": "模板X"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "settings.json").write_text(
        json.dumps({"ai": {"model": "gpt"}, "backup": {"keep": 3}, "polling": {"interval": 5}}),
        encoding="utf-8",
    )
    (data_dir / "activity.jsonl").write_text("{}\n", encoding="utf-8")
    arch = data_dir / "archive"
    arch.mkdir()
    (arch / "2026-01-05.log").write_text("jan\n", encoding="utf-8")
    (arch / "2026-02-10.log").write_text("feb\n", encoding="utf-8")
    rev = data_dir / "reviews"
    rev.mkdir()
    (rev / "plan-2026-01-01.md").write_text("plan\n", encoding="utf-8")
    (rev / "review-2026-01-01.md").write_text("review\n", encoding="utf-8")
    for name in ("foo", "bar"):
        d = data_dir / "plugins" / name
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(f'{{"name": "{name}"}}', encoding="utf-8")
    (data_dir / ".env").write_text("AI_API_KEY=secret\n", encoding="utf-8")


def _all_keys() -> list:
    return list(mig.INCLUDE_MAP.keys())


def test_parse_include_entries():
    assert mig._parse_include_entry("tasks") == ("tasks", None)
    assert mig._parse_include_entry("tasks:one-time") == ("tasks", "one-time")
    assert mig._parse_include_entry("tasks:bogus") is None  # 未知 task_type
    assert mig._parse_include_entry("settings:ai") == ("settings", "ai")
    assert mig._parse_include_entry("archive:2026-08") == ("archive", "2026-08")
    assert mig._parse_include_entry("archive:20268") is None  # 非月份
    assert mig._parse_include_entry("plugins:My-Dir") == ("plugins", "My-Dir")  # 大小写保留
    assert mig._parse_include_entry("history:sub") is None  # 不支持子键的类别
    # 裸键吞并同键子键；去重
    assert mig.parse_include_entries(["tasks:one-time", "tasks", "tasks:one-time"]) == [
        ("tasks", None)
    ]


def test_import_tasks_partition(tmp_path: Path):
    backup_root = tmp_path / "backup"
    live = tmp_path / "live"
    _seed_rich(backup_root)
    _seed_rich(live)
    # 本地：一次性不同、周期不同
    (live / "active_tasks.json").write_text(
        json.dumps(
            [
                {"id": "L1", "title": "一次性-本地", "task_type": "one-time"},
                {
                    "id": "L2",
                    "title": "周期-本地",
                    "task_type": "periodic_instance",
                    "template_id": "tpl-y",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    exported = mig.create_export_zip(["tasks"], data_dir=backup_root)
    assert exported.ok

    result = mig.import_replace(
        exported.path, ["tasks:one-time"], data_dir=live, make_safety_backup=False
    )
    assert result.ok, result.message
    assert result.include == ["tasks:one-time"]
    tasks = json.loads((live / "active_tasks.json").read_text(encoding="utf-8"))
    ids = {t["id"] for t in tasks}
    # 一次性整块换成备份的；周期实例保留本地
    assert ids == {"a1", "a2", "L2"}
    assert result.details["tasks"] == "replaced_partition"


def test_import_settings_partition(tmp_path: Path):
    backup_root = tmp_path / "backup"
    live = tmp_path / "live"
    _seed_rich(backup_root)
    _seed_rich(live)
    # 本地设置：ai 不同、多一个 appearance 节
    (live / "settings.json").write_text(
        json.dumps({"ai": {"model": "local"}, "appearance": {"skin": "neo"}}),
        encoding="utf-8",
    )
    exported = mig.create_export_zip(["settings"], data_dir=backup_root)
    assert exported.ok

    result = mig.import_replace(
        exported.path, ["settings:ai"], data_dir=live, make_safety_backup=False
    )
    assert result.ok, result.message
    settings = json.loads((live / "settings.json").read_text(encoding="utf-8"))
    assert settings["ai"] == {"model": "gpt"}  # 勾选节替换
    assert settings["appearance"] == {"skin": "neo"}  # 未勾选节保持
    assert "backup" not in settings and "polling" not in settings  # 未勾选节不带入


def test_import_dir_partitions(tmp_path: Path):
    backup_root = tmp_path / "backup"
    live = tmp_path / "live"
    _seed_rich(backup_root)
    _seed_rich(live)
    # 本地插件：foo 内容不同 + 多一个 baz；复盘/归档内容改写以验证分区边界
    (live / "plugins" / "foo" / "plugin.json").write_text('{"name": "local-foo"}', encoding="utf-8")
    (live / "plugins" / "baz").mkdir(parents=True, exist_ok=True)
    (live / "plugins" / "baz" / "plugin.json").write_text("{}", encoding="utf-8")
    (live / "reviews" / "plan-2026-01-01.md").write_text("local-plan", encoding="utf-8")
    (live / "reviews" / "review-2026-01-01.md").write_text("local-review", encoding="utf-8")
    (live / "archive" / "2026-01-05.log").write_text("local-jan\n", encoding="utf-8")
    (live / "archive" / "2026-02-10.log").write_text("local-feb\n", encoding="utf-8")
    exported = mig.create_export_zip(["plugins", "reviews", "archive"], data_dir=backup_root)
    assert exported.ok

    result = mig.import_replace(
        exported.path,
        ["plugins:foo", "reviews:plan", "archive:2026-01"],
        data_dir=live,
        make_safety_backup=False,
    )
    assert result.ok, result.message
    # plugins:foo 换成备份内容，未勾选的 bar/baz 均保持本地不动
    foo = (live / "plugins" / "foo" / "plugin.json").read_text(encoding="utf-8")
    assert foo == '{"name": "foo"}'
    bar = (live / "plugins" / "bar" / "plugin.json").read_text(encoding="utf-8")
    assert bar == '{"name": "bar"}'
    assert (live / "plugins" / "baz" / "plugin.json").exists()
    # reviews:plan 替换为备份内容，review 保持本地
    assert (live / "reviews" / "plan-2026-01-01.md").read_text(encoding="utf-8") == "plan\n"
    assert (live / "reviews" / "review-2026-01-01.md").read_text(encoding="utf-8") == "local-review"
    # archive:2026-01 替换，2026-02 保持本地
    assert (live / "archive" / "2026-01-05.log").read_text(encoding="utf-8") == "jan\n"
    assert (live / "archive" / "2026-02-10.log").read_text(encoding="utf-8") == "local-feb\n"
    assert set(result.include) == {"plugins:foo", "reviews:plan", "archive:2026-01"}


def test_import_bare_key_subsumes_subkey(tmp_path: Path):
    backup_root = tmp_path / "backup"
    live = tmp_path / "live"
    _seed_rich(backup_root)
    _seed_rich(live)
    exported = mig.create_export_zip(["tasks"], data_dir=backup_root)
    result = mig.import_replace(
        exported.path,
        ["tasks", "tasks:one-time"],
        data_dir=live,
        make_safety_backup=False,
    )
    assert result.ok
    tasks = json.loads((live / "active_tasks.json").read_text(encoding="utf-8"))
    assert {t["id"] for t in tasks} == {"a1", "a2", "p1"}  # 整文件替换
    assert result.include == ["tasks"]


def test_preview_import(tmp_path: Path):
    backup_root = tmp_path / "backup"
    _seed_rich(backup_root)
    exported = mig.create_export_zip(_all_keys(), data_dir=backup_root)
    assert exported.ok

    data = mig.preview_import(exported.path)
    assert data["ok"], data.get("message")
    cats = {c["key"]: c for c in data["categories"]}
    assert cats["tasks"]["counts"] == {"one-time": 2, "periodic_instance": 1}
    assert cats["tasks"]["templates"] == [{"template_id": "tpl-x", "title": "模板X", "count": 1}]
    assert cats["templates"]["count"] == 1
    assert cats["settings"]["sections"] == ["ai", "backup", "polling"]
    assert cats["reviews"]["counts"]["plan"] == 1
    assert cats["reviews"]["counts"]["review"] == 1
    assert cats["archive"]["months"] == [
        {"month": "2026-01", "files": 1},
        {"month": "2026-02", "files": 1},
    ]
    assert cats["plugins"]["plugins"] == ["bar", "foo"]
    assert cats["env"]["present"] is True
    assert data["manifest"]["include"]  # manifest 摘要带出

    # 缺密码 / 错密码
    enc = mig.create_export_zip(["tasks"], data_dir=backup_root, password="pw")
    assert enc.ok
    no_pw = mig.preview_import(enc.path)
    assert not no_pw["ok"] and no_pw["needs_password"]
    bad = mig.preview_import(enc.path, password="wrong")
    assert not bad["ok"] and "密码错误" in bad["message"]
    good = mig.preview_import(enc.path, password="pw")
    assert good["ok"]


# —— 加密（AES-256）/ 另存为 / 快照 / 轮转 ——


def test_export_encrypted_roundtrip(tmp_path: Path):
    src = tmp_path / "src"
    _seed(src)
    out = mig.create_export_zip(["tasks", "env"], data_dir=src, password="pw123")
    assert out.ok, out.message
    assert mig.is_encrypted_zip(out.path)

    # 无密码 → 拒绝；错密码 → 密码错误；对密码 → 成功
    dst = tmp_path / "dst"
    _seed(dst)
    no_pw = mig.import_replace(out.path, data_dir=dst, make_safety_backup=False)
    assert not no_pw.ok and "密码" in no_pw.message
    bad = mig.import_replace(out.path, data_dir=dst, password="wrong", make_safety_backup=False)
    assert not bad.ok and "密码错误" in bad.message
    ok = mig.import_replace(out.path, data_dir=dst, password="pw123", make_safety_backup=False)
    assert ok.ok, ok.message
    assert (dst / ".env").read_text(encoding="utf-8") == "AI_API_KEY=secret\n"


def test_export_plaintext_is_plain_zipfile(tmp_path: Path):
    """无密码导出必须保持 stdlib zipfile 可读（不设 encryption）。"""
    root = tmp_path / "data"
    _seed(root)
    out = mig.create_export_zip(data_dir=root)
    assert out.ok
    assert not mig.is_encrypted_zip(out.path)
    with zipfile.ZipFile(out.path) as zf:  # stdlib 直读
        assert "active_tasks.json" in zf.namelist()
    ok = mig.import_replace(out.path, data_dir=root, make_safety_backup=False)
    assert ok.ok


def test_export_out_path_save_as(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    dest = tmp_path / "elsewhere" / "mine.zip"
    out = mig.create_export_zip(["tasks"], data_dir=root, out_path=dest)
    assert out.ok, out.message
    assert out.path == str(dest)
    assert dest.is_file()


def test_import_legacy_v1_plaintext_package(tmp_path: Path):
    """手造无 encrypted 字段的 v1 明文老包仍可导入。"""
    src = tmp_path / "src"
    _seed(src)
    legacy = tmp_path / "legacy.zip"
    with zipfile.ZipFile(legacy, "w") as zf:
        zf.writestr("active_tasks.json", '[{"id":"t9","title":"old"}]')
        zf.writestr(
            "manifest.json",
            json.dumps({"format": "zentray-backup", "format_version": 1, "include": ["tasks"]}),
        )
    dst = tmp_path / "dst"
    _seed(dst)
    ok = mig.import_replace(legacy, data_dir=dst, make_safety_backup=False)
    assert ok.ok, ok.message
    tasks = json.loads((dst / "active_tasks.json").read_text(encoding="utf-8"))
    assert tasks[0]["id"] == "t9"


def test_list_backups_kinds_and_encrypted(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    bdir = tmp_path / "bk"
    # 显式 out_path：秒级时间戳在同秒内会同名互覆
    mig.create_export_zip(data_dir=root, out_path=bdir / "zentray-backup-a.zip")
    mig.create_export_zip(data_dir=root, out_path=bdir / "zentray-auto-b.zip")
    mig.create_export_zip(data_dir=root, out_path=bdir / "zentray-pre-import-c.zip")
    mig.create_export_zip(data_dir=root, out_path=bdir / "zentray-backup-d.zip", password="x")

    items = mig.list_backups(backup_dir=bdir)
    assert len(items) == 4
    assert any(i["kind"] == "auto" for i in items)
    assert any(i["kind"] == "manual" and i["encrypted"] for i in items)
    assert any(i["kind"] == "pre_import" for i in items)
    # 明文包 manifest 可读，加密包 manifest 为 None
    plain = next(i for i in items if i["kind"] == "manual" and not i["encrypted"])
    assert plain["manifest"]["include"]
    enc = next(i for i in items if i["encrypted"])
    assert enc["manifest"] is None


def test_delete_backup_rejects_outside_dir(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    bdir = tmp_path / "bk"
    mig.create_export_zip(data_dir=root, out_dir=bdir)
    outside = tmp_path / "other.zip"
    outside.write_bytes(b"pk")
    assert not mig.delete_backup(outside, backup_dir=bdir).ok
    inner = mig.list_backups(backup_dir=bdir)[0]
    assert mig.delete_backup(inner["path"], backup_dir=bdir).ok
    assert not Path(inner["path"]).exists()


def test_prune_only_auto_prefix(tmp_path: Path):
    root = tmp_path / "data"
    _seed(root)
    bdir = tmp_path / "bk"
    # 显式 out_path：秒级时间戳在同秒内会同名互覆
    for i in range(3):
        mig.create_export_zip(data_dir=root, out_path=bdir / f"{mig.AUTO_PREFIX}-{i}.zip")
    manual = mig.create_export_zip(data_dir=root, out_path=bdir / "zentray-backup-m.zip")
    assert manual.ok
    # keep=0 不轮转
    assert mig.prune_auto_backups(keep=0, backup_dir=bdir) == 0
    assert len(list(bdir.glob("*.zip"))) == 4
    # keep=2 → 只删 auto 最旧 1 份，manual 存活
    removed = mig.prune_auto_backups(keep=2, backup_dir=bdir)
    assert removed == 1
    assert len(list(bdir.glob(f"{mig.AUTO_PREFIX}-*.zip"))) == 2
    assert Path(manual.path).exists()
