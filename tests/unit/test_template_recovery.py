"""周期模板防丢：导入读取失败不动本地 + 主文件双失后从备份自愈。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pyzipper

from zentray.repositories.file_periodic_repository import FilePeriodicTemplateRepository
from zentray.services import data_migration as mig


def _seed_templates(root: Path, items: list) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "periodic_templates.json").write_text(
        json.dumps(items, ensure_ascii=False), encoding="utf-8"
    )


# —— 导入：包条目读取失败时本地文件必须原样保留 ————————————————


def test_import_read_failure_keeps_local(tmp_path, monkeypatch):
    src = tmp_path / "src"
    live = tmp_path / "live"
    _seed_templates(
        src,
        [{"template_id": "z1", "base_title": "备份模板", "periodicity": "daily", "category": "工作"}],
    )
    _seed_templates(
        live,
        [{"template_id": "L1", "base_title": "本地模板", "periodicity": "daily", "category": "工作"}],
    )
    exported = mig.create_export_zip(["templates"], data_dir=src)
    assert exported.ok

    orig_read = pyzipper.AESZipFile.read

    def boom(self, name, pwd=None):
        if name == "periodic_templates.json":
            raise zipfile.BadZipFile("Bad CRC-32 (simulated)")
        return orig_read(self, name, pwd)

    monkeypatch.setattr(pyzipper.AESZipFile, "read", boom)
    result = mig.import_replace(
        exported.path, ["templates"], data_dir=live, make_safety_backup=False
    )
    monkeypatch.undo()

    assert not result.ok
    kept = json.loads((live / "periodic_templates.json").read_text(encoding="utf-8"))
    assert [t["template_id"] for t in kept] == ["L1"], "读取失败不得删本地模板"


def test_import_replaces_file_and_mirrors_bak(tmp_path):
    src = tmp_path / "src"
    live = tmp_path / "live"
    _seed_templates(
        src,
        [{"template_id": "z1", "base_title": "备份模板", "periodicity": "daily", "category": "工作"}],
    )
    _seed_templates(
        live,
        [{"template_id": "L1", "base_title": "本地模板", "periodicity": "daily", "category": "工作"}],
    )
    exported = mig.create_export_zip(["templates"], data_dir=src)
    assert exported.ok

    result = mig.import_replace(
        exported.path, ["templates"], data_dir=live, make_safety_backup=False
    )
    assert result.ok, result.message
    got = json.loads((live / "periodic_templates.json").read_text(encoding="utf-8"))
    assert [t["template_id"] for t in got] == ["z1"]
    bak = live / "periodic_templates.json.bak"
    assert bak.exists(), "导入后应镜像 .bak 保住自愈链"
    assert json.loads(bak.read_text(encoding="utf-8")) == got


# —— 模板库：主文件与 .bak 双失 → 从最近备份自愈 ————————————————


def test_find_all_heals_from_latest_backup(tmp_path):
    root = tmp_path / "data"
    _seed_templates(
        root,
        [{"template_id": "t1", "base_title": "模板1", "periodicity": "daily", "category": "工作"}],
    )
    exported = mig.create_export_zip(["templates"], data_dir=root)
    assert exported.ok  # 备份落在 root/exports/

    fp = root / "periodic_templates.json"
    fp.unlink()
    (root / "periodic_templates.json.bak").unlink(missing_ok=True)

    repo = FilePeriodicTemplateRepository(fp)
    items = repo.find_all()
    assert [t.template_id for t in items] == ["t1"]
    assert fp.exists(), "自愈应回写主文件"
    assert (root / "periodic_templates.json.bak").exists(), "回写走 save_json_list 应带 .bak"


def test_find_all_keeps_explicit_empty(tmp_path):
    root = tmp_path / "data"
    _seed_templates(
        root,
        [{"template_id": "t1", "base_title": "模板1", "periodicity": "daily", "category": "工作"}],
    )
    assert mig.create_export_zip(["templates"], data_dir=root).ok

    fp = root / "periodic_templates.json"
    fp.write_text("[]", encoding="utf-8")  # 用户主动清空：文件存在

    repo = FilePeriodicTemplateRepository(fp)
    assert repo.find_all() == []
    assert fp.read_text(encoding="utf-8") == "[]", "显式空列表不得被备份回填"


def test_find_all_no_backup_gives_empty(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    repo = FilePeriodicTemplateRepository(root / "periodic_templates.json")
    assert repo.find_all() == []
    assert not (root / "periodic_templates.json").exists(), "无备份可愈时不落文件"
